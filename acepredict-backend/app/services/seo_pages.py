"""
Pages SEO par match (/fr/pronostic/<slug>) : création depuis les Fixture,
snapshot FIGE du pronostic, ajout du résultat réel après le match, pages
liste (hub, bilan, tournoi), sitemap et ping IndexNow.

Principes (cf. ARCHITECTURE/README SEO) :
  * le pronostic n'est JAMAIS recalculé après publication (snapshot JSON) ;
  * le résultat réel vient de la table Match (import Sackmann / sync_daily) ;
  * aucune donnée inventée : une section sans donnée est simplement omise ;
  * aucun appel LLM payant (analyse rédigée de façon déterministe).
"""
import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import prediction, score_projection, seo_render
from app.services.ai_narrative import _elo_to_level_pct

log = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")
MAX_NEW_PER_RUN = 60
LOOKAHEAD = timedelta(days=4)
MAX_RANK = 150

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MOIS_C = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

ROUNDS = {
    "f": "finale", "final": "finale", "finals": "finale",
    "sf": "demi-finale", "semifinal": "demi-finale", "semifinals": "demi-finale", "semi-finals": "demi-finale",
    "qf": "quart de finale", "quarterfinal": "quart de finale", "quarterfinals": "quart de finale", "quarter-finals": "quart de finale",
    "r16": "1/8 de finale", "1/8": "1/8 de finale", "round of 16": "1/8 de finale", "4th round": "1/8 de finale",
    "r32": "1/16 de finale", "1/16": "1/16 de finale", "round of 32": "1/16 de finale", "3rd round": "1/16 de finale",
    "r64": "1/32 de finale", "1/32": "1/32 de finale", "round of 64": "1/32 de finale", "2nd round": "1/32 de finale",
    "r128": "1er tour", "1/64": "1er tour", "round of 128": "1er tour", "1st round": "1er tour",
}

PLACEHOLDER_IMG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 112 140'><rect width='112' height='140' fill='%231f2e22'/>"
    "<circle cx='56' cy='52' r='22' fill='%23364a39'/><path d='M12 140c0-30 20-48 44-48s44 18 44 48z' fill='%23364a39'/></svg>"
)


# ------------------------------------------------------------------ utils --
def display_pct(raw: float) -> float:
    """Même repondération que l'application (visitennis_1.html::displayConfidencePct) :
    la probabilité réelle [50, 99] est étirée vers [70, 98] pour l'affichage."""
    clamped = min(99.0, max(50.0, raw))
    ratio = (clamped - 50.0) / (99.0 - 50.0)
    return round((70.0 + ratio * (98.0 - 70.0)) * 10) / 10


def slugify(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def round_label(r: Optional[str]) -> str:
    if not r:
        return "match"
    return ROUNDS.get(r.strip().lower(), r.strip())


def to_paris(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PARIS)


def fr_date_long(dt: datetime) -> str:
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]} {dt.year}"


def fr_date_pub(dt: datetime) -> str:
    return f"{dt.day} {MOIS[dt.month - 1]} {dt.year}"


def fr_date_short(dt: datetime) -> str:
    return f"{dt.day} {MOIS_C[dt.month - 1]} {dt.year}"


def _utc_iso(dt: Optional[datetime]) -> str:
    dt = dt or datetime.utcnow()
    return dt.replace(microsecond=0).isoformat() + "Z"


def match_key_for(tour, tournament, p1_id, p2_id, scheduled) -> str:
    a, b = sorted([str(p1_id), str(p2_id)])
    year = scheduled.year if scheduled else ""
    basis = f"{tour}|{slugify(tournament or '')}|{a}|{b}|{year}"
    return hashlib.sha1(basis.encode()).hexdigest()


def key_for_fixture(fx: models.Fixture) -> str:
    tid = fx.tournament_id_external or fx.tournament_name
    return match_key_for(fx.tour.value if fx.tour else "", tid, fx.player1_id, fx.player2_id, fx.scheduled_time)


# ----------------------------------------------------------------- photos --
def fetch_photo(name: str) -> Optional[str]:
    """Miniature Wikipédia (même source que le classement du site). None si
    introuvable/ambigu -- jamais d'exception."""
    try:
        title = name.strip().replace(" ", "_")
        r = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            timeout=6.0, headers={"User-Agent": "TennisMind/1.0 (https://app-tennismind.com)"},
        )
        if r.status_code != 200:
            return None
        j = r.json()
        if "tennis" not in (j.get("description", "") + j.get("extract", "")).lower():
            return None
        return (j.get("thumbnail") or {}).get("source")
    except Exception:
        return None


def photo_map(db: Session, player_ids) -> dict:
    ids = [str(i) for i in player_ids]
    if not ids:
        return {}
    return {r.player_id: r.url for r in db.query(models.PlayerPhoto).filter(models.PlayerPhoto.player_id.in_(ids)).all() if r.url}


def photo_for(db: Session, player) -> str:
    """Miniature en cache, sinon récupération (une fois) puis mise en cache."""
    row = db.get(models.PlayerPhoto, str(player.id))
    if row and (row.url or (row.fetched_at and row.fetched_at > datetime.utcnow() - timedelta(days=30))):
        return row.url or PLACEHOLDER_IMG
    url = fetch_photo(player.name)
    if row:
        row.url, row.fetched_at = url or "", datetime.utcnow()
    else:
        db.add(models.PlayerPhoto(player_id=str(player.id), url=url or "", fetched_at=datetime.utcnow()))
    db.commit()
    return url or PLACEHOLDER_IMG


def fill_photos(db: Session, limit: int = 40) -> int:
    """Remplit le cache pour les joueurs du top 100 (quelques-uns par passage)."""
    from app.services import seo_extra
    n = 0
    have = {r.player_id for r in db.query(models.PlayerPhoto.player_id).all()}
    for p in seo_extra.top_players(db):
        if str(p.id) in have:
            continue
        photo_for(db, p)
        n += 1
        if n >= limit:
            break
    return n


# ------------------------------------------------------------ player data --
def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def player_traits(db: Session, pid) -> dict:
    """Aces par match et % de points gagnés au retour, sur les 30 derniers
    matchs avec stats détaillées. Clés absentes si pas de donnée."""
    ms = (db.query(models.Match)
          .filter(or_(models.Match.player1_id == pid, models.Match.player2_id == pid),
                  models.Match.winner_id.isnot(None))
          .order_by(models.Match.tourney_date.desc()).limit(60).all())
    aces, ret_won, ret_tot, n = 0.0, 0.0, 0.0, 0
    for m in ms:
        st = m.stats or {}
        mine = "w" if m.winner_id == pid else "l"
        opp = "l" if mine == "w" else "w"
        ace = _num(st.get(f"{mine}_ace"))
        svpt, f1, f2 = _num(st.get(f"{opp}_svpt")), _num(st.get(f"{opp}_1stWon")), _num(st.get(f"{opp}_2ndWon"))
        if ace is None or not svpt or f1 is None or f2 is None:
            continue
        n += 1
        aces += ace
        ret_tot += svpt
        ret_won += svpt - f1 - f2
        if n >= 30:
            break
    if n < 5:
        return {}
    return {"ace": round(aces / n, 1), "ret": round(100 * ret_won / ret_tot)}


def surface_winrate(db: Session, pid, surface: str) -> Optional[int]:
    try:
        surf = models.SurfaceEnum(surface)
    except ValueError:
        return None
    since = datetime.utcnow() - timedelta(days=365)
    ms = (db.query(models.Match)
          .filter(or_(models.Match.player1_id == pid, models.Match.player2_id == pid),
                  models.Match.winner_id.isnot(None), models.Match.surface == surf,
                  models.Match.tourney_date >= since).all())
    if len(ms) < 5:
        return None
    return round(100 * sum(1 for m in ms if m.winner_id == pid) / len(ms))



def player_bio(p) -> dict:
    age = None
    if getattr(p, "birthdate", None):
        today = datetime.utcnow()
        age = today.year - p.birthdate.year - ((today.month, today.day) < (p.birthdate.month, p.birthdate.day))
    hand = {"R": "Droitier", "L": "Gaucher"}.get((p.hand or "").upper()[:1]) if getattr(p, "hand", None) else None
    return {"age": age, "taille": p.height_cm or None, "main": hand, "pays": p.country or None}


def record(db: Session, pid, since: Optional[datetime] = None) -> Optional[list]:
    q = db.query(models.Match).filter(or_(models.Match.player1_id == pid, models.Match.player2_id == pid),
                                      models.Match.winner_id.isnot(None))
    if since:
        q = q.filter(models.Match.tourney_date >= since)
    total = q.count()
    if total < 3:
        return None
    wins = q.filter(models.Match.winner_id == pid).count()
    return [wins, total - wins]


def extra_stats(db: Session, fx_or_pg_p1, fx_or_pg_p2, surface: str) -> dict:
    """Chiffres complémentaires (omis individuellement s'ils manquent)."""
    a, b = fx_or_pg_p1, fx_or_pg_p2
    since = datetime.utcnow() - timedelta(days=365)
    lv = lambda p: _elo_to_level_pct(p.elo_overall)
    return {
        "bio": [player_bio(a), player_bio(b)],
        "season": [record(db, a.id, since), record(db, b.id, since)],
        "career": [record(db, a.id), record(db, b.id)],
        "elo_all": [lv(a), lv(b)],
    }


def typical_scoreline(n_win: int, n_lose: int, gps: float) -> str:
    """Score en jeux "typique" cohérent avec le résultat en sets et le
    nombre moyen de jeux par set (illustratif, pas une prédiction jeu par jeu)."""
    w = "6-3" if gps < 9.7 else ("6-4" if gps < 10.6 else "7-5")
    l = "3-6" if gps < 9.7 else ("4-6" if gps < 10.6 else "5-7")
    seq, wl, ll = [], n_win, n_lose
    while wl or ll:
        if wl:
            seq.append(w); wl -= 1
        if ll and wl:
            seq.append(l); ll -= 1
        elif ll:
            seq.append(l); ll -= 1
    return " ".join(seq)


# --------------------------------------------------------------- snapshot --
def _eligible(fx: models.Fixture) -> bool:
    if not fx.tour or not fx.surface or fx.surface.value not in ("hard", "clay", "grass"):
        return False
    p1, p2 = fx.player1, fx.player2
    if not p1 or not p2:
        return False
    bad = models.DataConfidenceEnum.insufficient
    if p1.data_confidence == bad or p2.data_confidence == bad:
        return False
    ranks = [r for r in (p1.current_rank, p2.current_rank) if r]
    return bool(ranks) and min(ranks) <= MAX_RANK


def _analysis(snap: dict) -> list[str]:
    p = snap
    fav, opp = (p["p1"], p["p2"]) if p["pct1"] >= p["pct2"] else (p["p2"], p["p1"])
    fi = "1" if fav == p["p1"] else "2"
    oi = "2" if fi == "1" else "1"
    pf = max(p["pct1"], p["pct2"])
    rf = max(p.get("raw1", p["pct1"]), p.get("raw2", p["pct2"]))
    rank_txt = {"1": p.get("rank1"), "2": p.get("rank2")}
    surf = {"hard": "surface dure", "clay": "terre battue", "grass": "gazon"}[p["surface"]]
    lab = "grand favori" if rf >= 80 else ("favori" if rf >= 65 else ("léger favori" if rf >= 55 else "à peine favori"))
    s1 = f"{fav} aborde ce {p['round_label']} du {p['tournoi']} en {lab} ({str(pf).replace('.', ',')} %)."
    lv = p.get("levels") or {}
    if lv.get(fi) is not None and lv.get(oi) is not None:
        gap = lv[fi] - lv[oi]
        cmp_ = ("dépasse nettement" if gap >= 15 else "dépasse" if gap >= 6 else
                "est proche de" if gap > -6 else "est inférieur à")
        s1 += f" Son niveau TennisMind sur {surf} ({lv[fi]} sur 100) {cmp_} celui de {opp} ({lv[oi]} sur 100)."
    paras = [s1]
    form = p.get("form") or {}
    parts = []
    if form.get(fi) and form.get(oi):
        wf, wo = form[fi].count("V"), form[oi].count("V")
        parts.append(f"Sur ses {len(form[fi])} derniers matchs, {fav} compte {wf} victoire{'s' if wf > 1 else ''} contre {wo} pour {opp}.")
    h = p.get("h2h")
    if h and h["total"]:
        wins_fav = h["w1"] if fi == "1" else h["w2"]
        wins_opp = h["w2"] if fi == "1" else h["w1"]
        if wins_fav == wins_opp:
            parts.append(f"Les confrontations directes sont à égalité ({wins_fav}-{wins_opp}).")
        else:
            lead, a, b = (fav, wins_fav, wins_opp) if wins_fav > wins_opp else (opp, wins_opp, wins_fav)
            parts.append(f"{lead} mène {a}-{b} dans leurs confrontations directes.")
    if parts:
        paras.append(" ".join(parts))
    tail = f"{opp} n'est jamais hors de portée : "
    tail += f"statistiquement, environ un match sur {max(2, round(100 / max(1.0, 100 - rf)))} avec ce type d'écart tourne en faveur de l'outsider."
    if p.get("weather_adjusted"):
        tail += " Les conditions météo ont été prises en compte dans le calcul."
    paras.append(tail)
    return paras


def build_snapshot(db: Session, fx: models.Fixture) -> dict:
    from app.routers.analyses import _weather_from_fixture, _market_from_fixture

    p1, p2 = fx.player1, fx.player2
    surface = fx.surface.value
    weather = _weather_from_fixture(fx)
    market = _market_from_fixture(fx, p1.id)
    res = prediction.build_prediction(
        db, p1, p2, surface=surface, match_city=fx.city, match_date=fx.scheduled_time,
        tournament_name=fx.tournament_name, weather=weather, market=market, with_narrative=False,
    )
    d = res["detail"]
    pw = float(res["win_probability"])
    fav_is_p1 = str(res["predicted_winner_id"]) == str(p1.id)
    raw_fav = round(max(pw, 0.5) * 1000) / 10
    disp_fav = display_pct(raw_fav)
    pct1, pct2 = (disp_fav, round(100 - disp_fav, 1)) if fav_is_p1 else (round(100 - disp_fav, 1), disp_fav)
    raw1, raw2 = (raw_fav, round(100 - raw_fav, 1)) if fav_is_p1 else (round(100 - raw_fav, 1), raw_fav)

    ctx = d.get("tournament_context") or {}
    best_of = 5 if str(ctx.get("format", "")).startswith("Bo5") else 3
    sp = d.get("score_projection") or {}
    gps = ((sp.get("total_games") or {}).get("games_per_set")) or 10.0
    n = 3 if best_of == 5 else 2
    fav_pw = max(pw, 0.5)
    scores = []
    for sc in [s for s in score_projection.score_distribution(fav_pw, n) if s["side"] == "favorite"][:2]:
        k = int(sc["score"].split("-")[1])
        scores.append([sc["score"], typical_scoreline(n, k, gps), f"{round(sc['probability'] * 100)} %"])

    h2h = d.get("h2h")
    f1, f2 = d.get("form_player1"), d.get("form_player2")
    lv1, lv2 = _elo_to_level_pct(d.get("elo_player1")), _elo_to_level_pct(d.get("elo_player2"))
    tr1, tr2 = player_traits(db, p1.id), player_traits(db, p2.id)

    wx = None
    if weather is not None:
        wx = ({"roof": True} if weather.get("indoor") else {
            "roof": False, "temp_c": weather.get("temp_c"), "vent_kmh": weather.get("wind_kmh"),
            "hum_pct": weather.get("humidity_pct"), "desc": weather.get("description"),
        })
        if wx.get("temp_c") is not None:
            wx["temp_c"] = round(wx["temp_c"])
        if wx.get("vent_kmh") is not None:
            wx["vent_kmh"] = round(wx["vent_kmh"])

    snap = {
        "p1": p1.name, "p2": p2.name, "pct1": pct1, "pct2": pct2, "raw1": raw1, "raw2": raw2,
        "fav_id": str(res["predicted_winner_id"]),
        "rank1": f"N°{p1.current_rank} mondial" if p1.current_rank else "",
        "rank2": f"N°{p2.current_rank} mondial" if p2.current_rank else "",
        "img1": photo_for(db, p1),
        "img2": photo_for(db, p2),
        "tournoi": fx.tournament_name or "Tournoi",
        "round_label": round_label(fx.round),
        "surface": surface, "ville": fx.city or fx.tournament_name or "",
        "tier": ctx.get("tier"), "best_of": best_of,
        "scores": scores, "wx": wx,
        "traits": {"p1": tr1, "p2": tr2},
        "levels": {"1": lv1, "2": lv2},
        "form": {"1": [("V" if r == "V" else "D") for r in reversed((f1 or {}).get("results", []))],
                 "2": [("V" if r == "V" else "D") for r in reversed((f2 or {}).get("results", []))]},
        "h2h": ({"total": h2h["total"], "w1": h2h["wins_player1"], "w2": h2h["wins_player2"]} if h2h else None),
        "surf_wr": [surface_winrate(db, p1.id, surface), surface_winrate(db, p2.id, surface)],
        "weather_adjusted": bool(d.get("weather_adjustment")),
        "rk": [p1.current_rank, p2.current_rank],
        **extra_stats(db, p1, p2, surface),
    }
    snap["analyse"] = _analysis(snap)
    return snap


# ------------------------------------------------------------- create/sync --
def _unique_slug(db: Session, base: str, rnd: str) -> str:
    slug, i = base, 1
    while db.query(models.MatchPage.id).filter(models.MatchPage.slug == slug).first():
        slug = f"{base}-{slugify(rnd) or 'm'}" if i == 1 else f"{base}-{i}"
        i += 1
    return slug


def create_page(db: Session, fx: models.Fixture) -> Optional[models.MatchPage]:
    key = key_for_fixture(fx)
    if db.query(models.MatchPage.id).filter(models.MatchPage.match_key == key).first():
        return None
    snap = build_snapshot(db, fx)
    sched = to_paris(fx.scheduled_time)
    base = "-".join([slugify(snap["p1"]), slugify(snap["p2"]), slugify(fx.city or fx.tournament_name or ""),
                     sched.date().isoformat() if sched else "tba"]).strip("-")
    page = models.MatchPage(
        slug=_unique_slug(db, base, fx.round or ""), match_key=key,
        player1_id=fx.player1_id, player2_id=fx.player2_id, tour=fx.tour.value,
        tournament_name=fx.tournament_name,
        tournament_slug=f"{slugify(fx.tournament_name or 'tournoi')}-{(sched or datetime.utcnow()).year}",
        round=fx.round, scheduled_time=fx.scheduled_time, snapshot=snap,
        published_at=datetime.utcnow(), modified_at=datetime.utcnow(),
    )
    db.add(page)
    db.commit()
    return page


def attach_results(db: Session, now: Optional[datetime] = None) -> list[models.MatchPage]:
    """Ajoute le résultat réel aux pages dont le match est joué (table Match)."""
    now = now or datetime.utcnow()
    done = []
    pending = (db.query(models.MatchPage)
               .filter(models.MatchPage.finished_at.is_(None), models.MatchPage.scheduled_time < now)
               .all())
    for pg in pending:
        sched = pg.scheduled_time or now
        m = (db.query(models.Match)
             .filter(or_(and_(models.Match.player1_id == pg.player1_id, models.Match.player2_id == pg.player2_id),
                         and_(models.Match.player1_id == pg.player2_id, models.Match.player2_id == pg.player1_id)),
                     models.Match.winner_id.isnot(None),
                     models.Match.tourney_date >= sched - timedelta(days=14),
                     models.Match.tourney_date <= sched + timedelta(days=1),
                     or_(models.Match.created_at.is_(None), models.Match.created_at >= sched - timedelta(days=1)))
             .order_by(models.Match.tourney_date.desc()).first())
        if not m:
            continue
        pg.result_winner_id = m.winner_id
        pg.result_score = m.score
        pg.finished_at = now
        done.append(pg)
    if done:
        db.commit()
    return done



def enrich_snapshots(db: Session, limit: int = 500) -> int:
    """(1) Convertit les anciens snapshots (pourcentage brut) vers le
    pourcentage affiché comme dans l'application ; (2) ajoute les chiffres
    complémentaires aux pages créées avant leur introduction. Le pronostic
    (favori, probabilité réelle) n'est jamais modifié."""
    n = 0
    pages = db.query(models.MatchPage).limit(limit).all()
    for pg in pages:
        snap = dict(pg.snapshot or {})
        changed = False
        if "raw1" not in snap:
            snap["raw1"], snap["raw2"] = snap["pct1"], snap["pct2"]
            fav1 = snap["pct1"] >= snap["pct2"]
            disp = display_pct(max(snap["pct1"], snap["pct2"]))
            snap["pct1"], snap["pct2"] = (disp, round(100 - disp, 1)) if fav1 else (round(100 - disp, 1), disp)
            snap["analyse"] = _analysis(snap)
            changed = True
        if pg.finished_at is None and "bio" not in snap:
            p1, p2 = db.get(models.Player, pg.player1_id), db.get(models.Player, pg.player2_id)
            if p1 and p2:
                snap.update(extra_stats(db, p1, p2, snap["surface"]))
                changed = True
        if changed:
            pg.snapshot = snap
            n += 1
    if n:
        db.commit()
    return n


def ping_indexnow(urls: list[str]) -> bool:
    key = settings.indexnow_key
    if not key or not urls:
        return False
    base = settings.public_site_url.rstrip("/")
    try:
        r = httpx.post("https://api.indexnow.org/IndexNow", timeout=10.0, json={
            "host": base.replace("https://", "").replace("http://", ""),
            "key": key, "keyLocation": f"{base}/seo/indexnow-key.txt", "urlList": urls[:10000],
        })
        return r.status_code in (200, 202)
    except Exception as e:  # jamais bloquant
        log.warning("IndexNow KO: %s", e)
        return False


def sync_match_pages(db: Session, now: Optional[datetime] = None) -> dict:
    """Appelé en fin de sync_hourly : crée les nouvelles pages, met à jour
    l'horaire, ajoute les résultats, notifie IndexNow."""
    now = now or datetime.utcnow()
    stats = {"created": 0, "skipped": 0, "errors": 0, "finished": 0, "retimed": 0}
    new_urls = []
    fixtures = (db.query(models.Fixture)
                .filter(models.Fixture.scheduled_time >= now - timedelta(hours=2),
                        models.Fixture.scheduled_time <= now + LOOKAHEAD)
                .order_by(models.Fixture.scheduled_time).all())
    for fx in fixtures:
        try:
            if not _eligible(fx):
                stats["skipped"] += 1
                continue
            existing = db.query(models.MatchPage).filter(models.MatchPage.match_key == key_for_fixture(fx)).first()
            if existing:
                if existing.finished_at is None and fx.scheduled_time and existing.scheduled_time != fx.scheduled_time:
                    existing.scheduled_time = fx.scheduled_time
                    db.commit()
                    stats["retimed"] += 1
                continue
            if stats["created"] >= MAX_NEW_PER_RUN:
                continue
            pg = create_page(db, fx)
            if pg:
                stats["created"] += 1
                new_urls.append(f"{settings.public_site_url.rstrip('/')}/fr/pronostic/{pg.slug}")
        except Exception as e:
            db.rollback()
            stats["errors"] += 1
            log.warning("Page SEO ignorée (%s): %s", getattr(fx, "id", "?"), e)
    try:
        from app.services import seo_extra
        stats["retro"] = seo_extra.sync_retro_pages(db)
    except Exception as e:
        db.rollback()
        log.warning("Pages rétrospectives KO: %s", e)
    try:
        stats["photos"] = fill_photos(db)
    except Exception as e:
        db.rollback()
        log.warning("Photos SEO KO: %s", e)
    try:
        stats["enriched"] = enrich_snapshots(db)
    except Exception as e:
        db.rollback()
        log.warning("Enrichissement SEO KO: %s", e)
    try:
        finished = attach_results(db, now)
        stats["finished"] = len(finished)
        new_urls += [f"{settings.public_site_url.rstrip('/')}/fr/pronostic/{p.slug}" for p in finished]
    except Exception as e:
        db.rollback()
        log.warning("Résultats SEO KO: %s", e)
    if new_urls:
        stats["indexnow"] = ping_indexnow(new_urls)
    return stats


# ----------------------------------------------------------------- render --
def accuracy(db: Session, tournament_slug: Optional[str] = None) -> Optional[dict]:
    q = db.query(models.MatchPage).filter(models.MatchPage.finished_at.isnot(None), ~models.MatchPage.match_key.like("retro|%"))
    if tournament_slug:
        q = q.filter(models.MatchPage.tournament_slug == tournament_slug)
    pages = q.all()
    if not pages:
        return None
    ok = sum(1 for p in pages if str(p.result_winner_id) == str((p.snapshot or {}).get("fav_id")))
    return {"ok": ok, "total": len(pages), "pct": round(100 * ok / len(pages), 1)}


def _row(pg: models.MatchPage) -> dict:
    s = pg.snapshot
    sched = to_paris(pg.scheduled_time)
    done = pg.finished_at is not None
    retro = (pg.match_key or "").startswith("retro|")
    return {
        "slug": pg.slug, "p1": s["p1"], "p2": s["p2"], "pct": max(s["pct1"], s["pct2"]),
        "tournoi": s["tournoi"], "round": s.get("round_label", ""),
        "time": "" if retro else (sched.strftime("%H:%M") if sched else ""),
        "day": (f"Édition {sched.year}" if retro else (f"{JOURS[sched.weekday()]} {sched.day} {MOIS[sched.month - 1]}" if sched else "")),
        "img1": s.get("img1", ""), "img2": s.get("img2", ""),
        "done": done, "ok": done and str(pg.result_winner_id) == str(s["fav_id"]), "score": pg.result_score,
    }


def build_context(db: Session, pg: models.MatchPage) -> tuple[dict, str]:
    s = pg.snapshot
    sched = to_paris(pg.scheduled_time) or datetime.now(PARIS)
    pub = to_paris(pg.published_at) or sched
    done = pg.finished_at is not None
    fav_name = s["p1"] if s["pct1"] >= s["pct2"] else s["p2"]
    pf = max(s.get("raw1", s["pct1"]), s.get("raw2", s["pct2"])) / 100
    tour = (pg.tour or "atp").upper()
    tier = {"Grand Chelem": "Grand Chelem", "Masters 1000 / WTA 1000 / Finals": "1000 / Finals"}.get(s.get("tier"), "")
    rk = s.get("rk") or [None, None]
    st = {"rank": [str(rk[0]), str(rk[1])] if rk[0] and rk[1] else None}
    if s["levels"]["1"] is not None and s["levels"]["2"] is not None:
        st["elo"] = [f"{s['levels']['1']} / 100", f"{s['levels']['2']} / 100"]
    if s["form"]["1"] and s["form"]["2"]:
        st["form"] = [s["form"]["1"], s["form"]["2"]]
    if s.get("h2h"):
        st["h2h"] = [str(s["h2h"]["w1"]), str(s["h2h"]["w2"])]
    if all(v is not None for v in s.get("surf_wr", [None, None])):
        st["surf"] = [str(s["surf_wr"][0]), str(s["surf_wr"][1])]
    for k in ("season", "career"):
        v = s.get(k)
        if v and v[0] and v[1]:
            st[k] = [f"{v[0][0]}-{v[0][1]}", f"{v[1][0]}-{v[1][1]}"]
    if s.get("elo_all") and None not in s["elo_all"]:
        st["elo_all"] = [f"{x} / 100" for x in s["elo_all"]]
    bio = s.get("bio")
    if bio:
        for k in ("age", "taille", "main", "pays"):
            st[k] = [bio[0].get(k), bio[1].get(k)]
    tr = s.get("traits") or {}
    for k in ("ace", "ret"):
        a, b = (tr.get("p1") or {}).get(k), (tr.get("p2") or {}).get(k)
        if a is not None and b is not None:
            st["aces" if k == "ace" else "ret"] = [str(a).replace(".", ","), str(b)] if k == "ace" else [a, b]
    # Autres pronostics du même jour (liens internes)
    day_start = sched.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    others = (db.query(models.MatchPage)
              .filter(models.MatchPage.id != pg.id, ~models.MatchPage.match_key.like("retro|%"),
                      models.MatchPage.scheduled_time >= day_start - timedelta(hours=1),
                      models.MatchPage.scheduled_time < day_start + timedelta(hours=25))
              .order_by(models.MatchPage.scheduled_time).limit(4).all())
    related = [_row(o) for o in others]
    from app.services import seo_extra
    links = []
    for pid in (pg.player1_id, pg.player2_id):
        pl = db.get(models.Player, pid)
        if seo_extra.player_page_ok(pl):
            links.append((f"Fiche de {pl.name}", f"/fr/joueur/{seo_extra.player_slug(pl)}"))
    ev = seo_extra.evergreen_for(s.get("tournoi"))
    if ev:
        links.append((f"Pronostics {seo_extra.T[ev]['name']}", f"/fr/tournoi/{ev}"))
    links.append(("Pronostics du jour", "/fr/pronostics/aujourdhui"))

    d = {
        "img1": s["img1"], "img2": s["img2"], "p1": s["p1"], "p2": s["p2"],
        "raw_pf": pf * 100, "pct1": s["pct1"], "pct2": s["pct2"], "rank1": s["rank1"], "rank2": s["rank2"],
        "rank_label": f"Classement {tour}",
        "tournoi": s["tournoi"], "round": s["round_label"][:1].upper() + s["round_label"][1:],
        "tour_lbl": f"{tour} {tier}".strip(), "surface": s["surface"], "ville": s["ville"],
        "date_court": fr_date_short(sched), "date_long": fr_date_long(sched), "heure": sched.strftime("%H:%M"),
        "iso": sched.isoformat(), "slug": pg.slug,
        "publie": fr_date_pub(pub), "publie_iso": pub.isoformat(),
        "modif_iso": _utc_iso(pg.modified_at), "tournoi_slug": pg.tournament_slug,
        "st": st, "analyse": s["analyse"], "related": related, "links": links, "best_of": s["best_of"],
        "scores": [tuple(x) for x in s["scores"]], "wx": s.get("wx"),
        "traits": s.get("traits") or {}, "tease": None,
        "winner": None, "score": None, "actual": None,
    }
    if (pg.match_key or "").startswith("retro|"):
        d["retro"] = True
        d["year"] = sched.year
        d["date_long"] = f"Édition {sched.year}"
        d["heure"] = ""
    if done:
        winner_is_p1 = str(pg.result_winner_id) == str(pg.player1_id)
        d["winner"] = s["p1"] if winner_is_p1 else s["p2"]
        d["score"] = " ".join((pg.result_score or "").split())
        n = 3 if s["best_of"] == 5 else 2
        act = seo_render.sets_of(d["score"])
        prob = None
        for sc in score_projection.score_distribution(max(pf, 0.5), n):
            fav_wins = d["winner"] == fav_name
            if (sc["side"] == "favorite") == fav_wins and sc["score"] == act:
                prob = sc["probability"]
                break
        d["actual"] = {"sets": f"{round(prob * 100)} %" if prob is not None else "—"}
    return d, ("after" if done else "before")


def render_page(db: Session, pg: models.MatchPage) -> str:
    d, state = build_context(db, pg)
    return seo_render.render(d, state)


def render_hub(db: Session) -> str:
    now = datetime.utcnow()
    up = (db.query(models.MatchPage).filter(models.MatchPage.finished_at.is_(None), ~models.MatchPage.match_key.like("retro|%"),
                                            models.MatchPage.scheduled_time >= now - timedelta(hours=6))
          .order_by(models.MatchPage.scheduled_time).limit(60).all())
    rec = (db.query(models.MatchPage).filter(models.MatchPage.finished_at.isnot(None), ~models.MatchPage.match_key.like("retro|%"))
           .order_by(models.MatchPage.scheduled_time.desc()).limit(60).all())
    return seo_render.hub_page([_row(p) for p in up], [_row(p) for p in rec], accuracy(db))


def render_bilan(db: Session) -> str:
    rec = (db.query(models.MatchPage).filter(models.MatchPage.finished_at.isnot(None), ~models.MatchPage.match_key.like("retro|%"))
           .order_by(models.MatchPage.scheduled_time.desc()).limit(100).all())
    return seo_render.bilan_page(accuracy(db), [_row(p) for p in rec])


def render_tournoi(db: Session, slug: str) -> Optional[str]:
    from app.services import seo_extra
    if slug in seo_extra.T:
        return seo_extra.render_evergreen(db, slug)
    pages = (db.query(models.MatchPage).filter(models.MatchPage.tournament_slug == slug)
             .order_by(models.MatchPage.scheduled_time).all())
    if not pages:
        return None
    name = pages[0].tournament_name or slug
    up = [_row(p) for p in pages if p.finished_at is None]
    dn = [_row(p) for p in reversed(pages) if p.finished_at is not None]
    from app.services import seo_extra
    return seo_render.tournoi_page(name, slug, up, dn, accuracy(db, slug), seo_extra.finals_section(pages))


def render_sitemap(db: Session) -> str:
    entries = [("/fr/pronostics", datetime.utcnow().date().isoformat(), "hourly"),
               ("/fr/bilan", datetime.utcnow().date().isoformat(), "daily")]
    seen = set()
    for slug, mod in (db.query(models.MatchPage.tournament_slug, models.MatchPage.modified_at)
                      .order_by(models.MatchPage.modified_at.desc()).all()):
        if slug and slug not in seen:
            seen.add(slug)
            entries.append((f"/fr/tournoi/{slug}", (mod or datetime.utcnow()).date().isoformat(), "daily"))
    for slug, mod in (db.query(models.MatchPage.slug, models.MatchPage.modified_at)
                      .order_by(models.MatchPage.scheduled_time.desc()).limit(5000).all()):
        entries.append((f"/fr/pronostic/{slug}", (mod or datetime.utcnow()).date().isoformat(), "hourly"))
    from app.services import seo_extra
    entries += seo_extra.sitemap_entries(db)
    return seo_render.sitemap_xml(entries)

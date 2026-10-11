"""
Pages SEO "evergreen" et de découverte :
  * /fr/tournoi/<slug> pour les grands tournois (Grand Chelems, Masters 1000) ;
  * /fr/joueur/<slug> pour les joueurs du top 100 ;
  * /fr/tournois, /fr/joueurs (annuaires) ;
  * /fr/pronostics/aujourdhui|demain.
Contenu = faits stables sur le tournoi/joueur + données réelles de la base
(favoris par Elo de surface, prochains pronostics, résultats). Rien d'inventé.
"""
import html
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.services import seo_render as R
from app.services import seo_pages as P
from app.services.ai_narrative import _elo_to_level_pct

BASE = R.BASE
SURF_LABEL = {"hard": "dur", "clay": "terre battue", "grass": "gazon"}
SURF_FIELD = {"hard": "elo_hard", "clay": "elo_clay", "grass": "elo_grass"}
MAX_PLAYER_RANK = 100

T = {
    "australian-open": dict(name="Open d'Australie", keys=["australian-open"], city="Melbourne", surface="hard",
        level="Grand Chelem", when="janvier", tours=("atp", "wta"), bo5=True,
        blurb="L'Open d'Australie se joue à Melbourne Park, en janvier. Il ouvre la saison du Grand Chelem et se dispute sur surface dure."),
    "roland-garros": dict(name="Roland-Garros", keys=["roland-garros", "french-open"], city="Paris", surface="clay",
        level="Grand Chelem", when="fin mai et début juin", tours=("atp", "wta"), bo5=True,
        blurb="Roland-Garros se joue à Paris sur terre battue, de fin mai à début juin. C'est le seul Grand Chelem sur cette surface, où les échanges sont plus longs et l'endurance compte autant que la puissance."),
    "wimbledon": dict(name="Wimbledon", keys=["wimbledon"], city="Londres", surface="grass",
        level="Grand Chelem", when="fin juin et juillet", tours=("atp", "wta"), bo5=True,
        blurb="Wimbledon se joue à Londres, à l'All England Club, sur gazon. C'est le seul Grand Chelem sur cette surface, rapide, où le service et les points courts prennent beaucoup d'importance."),
    "us-open": dict(name="US Open", keys=["us-open"], city="New York", surface="hard",
        level="Grand Chelem", when="fin août et septembre", tours=("atp", "wta"), bo5=True,
        blurb="L'US Open se joue à New York, sur surface dure, de fin août à septembre. C'est le dernier Grand Chelem de la saison."),
    "indian-wells": dict(name="Indian Wells", keys=["indian-wells"], city="Indian Wells", surface="hard",
        level="Masters 1000 / WTA 1000", when="mars", tours=("atp", "wta"), bo5=False,
        blurb="Le tournoi d'Indian Wells se joue en Californie, sur surface dure, en mars. Il fait partie des plus gros tournois hors Grand Chelem."),
    "miami": dict(name="Masters de Miami", keys=["miami", "miami-open"], city="Miami", surface="hard",
        level="Masters 1000 / WTA 1000", when="fin mars et début avril", tours=("atp", "wta"), bo5=False,
        blurb="Le Masters de Miami se joue en Floride, sur surface dure, à la fin du mois de mars."),
    "monte-carlo": dict(name="Masters de Monte-Carlo", keys=["monte-carlo"], city="Monte-Carlo", surface="clay",
        level="Masters 1000", when="avril", tours=("atp",), bo5=False,
        blurb="Le Masters de Monte-Carlo se joue sur terre battue, en avril. Il lance la saison sur terre battue européenne."),
    "madrid": dict(name="Masters de Madrid", keys=["madrid", "madrid-open"], city="Madrid", surface="clay",
        level="Masters 1000 / WTA 1000", when="fin avril et mai", tours=("atp", "wta"), bo5=False,
        blurb="Le tournoi de Madrid se joue sur terre battue, en altitude, ce qui rend la balle plus vive que sur d'autres tournois de la surface."),
    "rome": dict(name="Masters de Rome", keys=["rome", "italian-open", "internazionali"], city="Rome", surface="clay",
        level="Masters 1000 / WTA 1000", when="mai", tours=("atp", "wta"), bo5=False,
        blurb="Le tournoi de Rome se joue sur terre battue, en mai, juste avant Roland-Garros. C'est l'un des derniers tests avant le Grand Chelem parisien."),
    "canada": dict(name="Masters du Canada", keys=["canada", "canadian-open", "toronto", "montreal", "national-bank-open"], city="Toronto / Montréal", surface="hard",
        level="Masters 1000 / WTA 1000", when="août", tours=("atp", "wta"), bo5=False,
        blurb="Le tournoi du Canada se joue sur surface dure, en août, en alternance entre Toronto et Montréal. Il lance la tournée nord-américaine avant l'US Open."),
    "cincinnati": dict(name="Masters de Cincinnati", keys=["cincinnati"], city="Cincinnati", surface="hard",
        level="Masters 1000 / WTA 1000", when="août", tours=("atp", "wta"), bo5=False,
        blurb="Le tournoi de Cincinnati se joue sur surface dure, en août, juste avant l'US Open."),
    "shanghai": dict(name="Masters de Shanghai", keys=["shanghai"], city="Shanghai", surface="hard",
        level="Masters 1000", when="octobre", tours=("atp",), bo5=False,
        blurb="Le Masters de Shanghai se joue sur surface dure, en octobre, en fin de saison asiatique."),
    "paris-bercy": dict(name="Masters de Paris-Bercy", keys=["paris", "paris-bercy", "bercy"], city="Paris", surface="hard",
        level="Masters 1000", when="fin octobre et début novembre", tours=("atp",), bo5=False,
        blurb="Le Masters de Paris-Bercy se joue en salle, sur surface dure, à la fin octobre. C'est le dernier Masters 1000 de la saison."),
}


def evergreen_for(tournament_name: Optional[str]) -> Optional[str]:
    if not tournament_name:
        return None
    s = f"-{P.slugify(tournament_name)}-"
    for slug, t in T.items():
        for k in t["keys"]:
            if f"-{k}-" in s:
                return slug
    return None


def player_slug(p) -> str:
    return P.slugify(p.name)


def player_page_ok(p) -> bool:
    return bool(p and p.current_rank and p.current_rank <= MAX_PLAYER_RANK
                and p.data_confidence != models.DataConfidenceEnum.insufficient)


def _tour(p) -> str:
    return p.tour.value.upper() if hasattr(p.tour, "value") else str(p.tour).upper()


def _crumbs(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + u} for i, (n, u) in enumerate(items)]}


def _crumb_html(items):
    out = ['<a href="/">Accueil</a>']
    for n, u in items[1:-1]:
        out.append(f'<a href="{u}">{html.escape(n)}</a>')
    out.append(html.escape(items[-1][0]))
    return '<nav class="crumb">' + " › ".join(out) + '</nav>'


# ------------------------------------------------------------ tournaments --
def _favorites(db: Session, surface: str, tour: str, n: int = 8):
    f = SURF_FIELD[surface]
    col = getattr(models.Player, f)
    q = (db.query(models.Player)
         .filter(models.Player.tour == tour, models.Player.current_rank.isnot(None),
                 models.Player.current_rank <= 150,
                 models.Player.data_confidence.in_([models.DataConfidenceEnum.high, models.DataConfidenceEnum.medium]),
                 col.isnot(None), col != 1500.0)
         .order_by(col.desc()).limit(n))
    return q.all()


def _fav_table(db, surface, tour, title):
    ps = _favorites(db, surface, tour)
    if len(ps) < 3:
        return ''
    rows = []
    for i, p in enumerate(ps, 1):
        name = html.escape(p.name)
        if player_page_ok(p):
            name = f'<a href="/fr/joueur/{player_slug(p)}">{name}</a>'
        lv = _elo_to_level_pct(getattr(p, SURF_FIELD[surface]))
        rows.append(f'<tr><td>{i}</td><td style="text-align:left">{name}</td><td>{lv} / 100</td></tr>')
    return (f'<h3 style="font-size:15px;margin:18px 0 8px">{title}</h3><table><tr><th>#</th><th style="text-align:left">Joueur</th>'
            f'<th>Note sur {SURF_LABEL[surface]}</th></tr>' + ''.join(rows) + '</table>')


FINAL_ROUNDS = {"finale": 0, "demi-finale": 1, "quart de finale": 2}


def finals_section(pages) -> str:
    """Gros matchs du tableau (finale, demies, quarts) : pronostic publié
    avant le match et résultat réel dès qu'il est joué."""
    sel = [x for x in pages if (x.snapshot or {}).get("round_label") in FINAL_ROUNDS]
    if not sel:
        return ''
    sel.sort(key=lambda x: (FINAL_ROUNDS[x.snapshot["round_label"]], x.scheduled_time or datetime.min))
    done = [x for x in sel if x.finished_at]
    ok = sum(1 for x in done if str(x.result_winner_id) == str(x.snapshot.get("fav_id")))
    head = ''
    if done:
        head = f'<p class="pend" style="margin:0 0 14px">Sur les phases finales déjà jouées, {ok} pronostic{"s" if ok > 1 else ""} sur {len(done)} {"sont justes" if ok > 1 else "est juste"}.</p>'
    return ('<section class="card"><h2>Phases finales : pronostics et résultats</h2>' + head
            + ''.join(R._row(P._row(x)) for x in sel) + '</section>')


def _edition_pages(db: Session, t: dict):
    slug = next(k for k, v in T.items() if v is t)
    names = [n for (n,) in db.query(models.MatchPage.tournament_name).distinct().all() if evergreen_for(n) == slug]
    if not names:
        return []
    return (db.query(models.MatchPage).filter(models.MatchPage.tournament_name.in_(names), ~models.MatchPage.match_key.like("retro|%"))
            .order_by(models.MatchPage.scheduled_time).all())


def _retro_selection(db: Session, slug: str):
    since = datetime.utcnow() - timedelta(days=365 * 7)
    rows = (db.query(models.Match, models.Competition)
            .join(models.Competition, models.Match.competition_id == models.Competition.id)
            .filter(models.Match.round.in_(["F", "SF", "QF"]), models.Match.winner_id.isnot(None),
                    models.Match.tourney_date >= since).all())
    rows = [(m, c) for m, c in rows if evergreen_for(c.name) == slug and m.tourney_date]
    if not rows:
        return []
    years = sorted({m.tourney_date.year for m, _ in rows}, reverse=True)
    latest = years[0]
    sel = [(m, c) for m, c in rows if (m.round == "F" and m.tourney_date.year in years[:6])
           or (m.tourney_date.year == latest and m.round in ("SF", "QF"))]
    order = {"F": 0, "SF": 1, "QF": 2}
    return sorted(sel, key=lambda x: (-x[0].tourney_date.year, order[x[0].round]))


def build_retro_snapshot(db: Session, m, slug: str):
    """Snapshot d'une analyse RÉTROSPECTIVE : niveaux actuels des joueurs sur la
    surface (pas de niveau avant-match en base), jamais comptée dans le bilan."""
    from app.services.elo import expected_score
    t = T[slug]
    w = db.get(models.Player, m.winner_id)
    l = db.get(models.Player, m.player2_id if m.winner_id == m.player1_id else m.player1_id)
    if not w or not l:
        return None
    surf = m.surface.value if m.surface else t["surface"]
    if surf not in SURF_FIELD:
        surf = t["surface"]
    f = SURF_FIELD[surf]
    pw = expected_score(getattr(w, f) or 1500.0, getattr(l, f) or 1500.0)
    fav_w = pw >= 0.5
    raw_fav = round(max(pw, 1 - pw) * 1000) / 10
    disp = P.display_pct(raw_fav)
    pct1, pct2 = (disp, round(100 - disp, 1)) if fav_w else (round(100 - disp, 1), disp)
    raw1, raw2 = (raw_fav, round(100 - raw_fav, 1)) if fav_w else (round(100 - raw_fav, 1), raw_fav)
    best_of = 5 if (t["bo5"] and w.tour == models.TourEnum.atp) else 3
    n = 3 if best_of == 5 else 2
    scores = []
    for sc in [x for x in P.score_projection.score_distribution(max(pw, 1 - pw), n) if x["side"] == "favorite"][:2]:
        scores.append([sc["score"], P.typical_scoreline(n, int(sc["score"].split("-")[1]), 10.0), f"{round(sc['probability'] * 100)} %"])
    snap = {
        "p1": w.name, "p2": l.name, "pct1": pct1, "pct2": pct2, "raw1": raw1, "raw2": raw2,
        "fav_id": str(w.id if fav_w else l.id), "rank1": "", "rank2": "",
        "img1": P.photo_for(db, w), "img2": P.photo_for(db, l),
        "tournoi": t["name"], "round_label": {"F": "finale", "SF": "demi-finale", "QF": "quart de finale"}[m.round],
        "surface": surf, "ville": t["city"], "tier": t["level"], "best_of": best_of, "scores": scores, "wx": None,
        "traits": {"p1": {}, "p2": {}}, "levels": {"1": _elo_to_level_pct(getattr(w, f)), "2": _elo_to_level_pct(getattr(l, f))},
        "form": {"1": [], "2": []}, "h2h": None, "surf_wr": [None, None], "weather_adjusted": False, "tease": None,
        "rk": [None, None], "retro": True,
    }
    snap["analyse"] = P._analysis(snap)
    return snap, w, l


def sync_retro_pages(db: Session, limit: int = 40) -> int:
    """Crée (quelques-unes par passage) les pages d'analyse rétrospective des
    grands matchs des tournois evergreen."""
    created = 0
    for slug in T:
        for m, c in _retro_selection(db, slug):
            key = f"retro|{m.id}"
            if db.query(models.MatchPage.id).filter(models.MatchPage.match_key == key).first():
                continue
            built = build_retro_snapshot(db, m, slug)
            if not built:
                continue
            snap, w, l = built
            year = m.tourney_date.year
            base = "-".join([P.slugify(w.name), P.slugify(l.name), slug, str(year), P.slugify(snap["round_label"])])
            pg = models.MatchPage(
                slug=P._unique_slug(db, base, m.round), match_key=key, player1_id=w.id, player2_id=l.id,
                tour=w.tour.value, tournament_name=T[slug]["name"], tournament_slug=f"{slug}-{year}",
                round=m.round, scheduled_time=m.tourney_date, snapshot=snap,
                published_at=datetime.utcnow(), modified_at=datetime.utcnow(),
                result_winner_id=m.winner_id, result_score=m.score, finished_at=datetime.utcnow())
            db.add(pg)
            db.commit()
            created += 1
            if created >= limit:
                return created
    return created


def _retro_pages(db: Session, slug: str):
    t = T[slug]
    names = [t["name"]]
    return (db.query(models.MatchPage)
            .filter(models.MatchPage.match_key.like("retro|%"), models.MatchPage.tournament_slug.like(f"{slug}-____"))
            .order_by(models.MatchPage.scheduled_time.desc()).all())


def retro_sections(db: Session, slug: str) -> str:
    pages = _retro_pages(db, slug)
    if not pages:
        return ''
    note = ('<p class="pend" style="margin:0 0 14px">Analyse du modèle (niveau des joueurs sur la surface), calculée après coup avec leurs niveaux actuels : '
            'ce n\'est pas un pronostic publié avant le match et elle n\'entre pas dans le bilan public.</p>')
    finals = [x for x in pages if x.round == "F"]
    latest_year = max(x.scheduled_time.year for x in pages)
    others = [x for x in pages if x.round != "F" and x.scheduled_time.year == latest_year]
    h = ''
    if finals:
        ok = sum(1 for x in finals if str(x.result_winner_id) == str(x.snapshot.get("fav_id")))
        h += ('<section class="card"><h2>Les dernières finales : analyse et résultat</h2>' + note
              + f'<p class="pend" style="margin:0 0 14px">Le modèle désigne le bon vainqueur sur {ok} finale{"s" if ok > 1 else ""} sur {len(finals)}.</p>'
              + R._grouped([P._row(x) for x in finals]) + '</section>')
    if others:
        rows = []
        for x in others:
            r = P._row(x)
            r["day"] = {"demi-finale": "Demi-finales", "quart de finale": "Quarts de finale"}.get(x.snapshot.get("round_label"), "")
            rows.append(r)
        rows.sort(key=lambda r: 0 if r["day"] == "Demi-finales" else 1)
        h += f'<section class="card"><h2>Édition {latest_year} : demi-finales et quarts de finale</h2>' + note + R._grouped(rows) + '</section>'
    return h


def render_evergreen(db: Session, slug: str) -> Optional[str]:
    t = T.get(slug)
    if not t:
        return None
    surf = SURF_LABEL[t["surface"]]
    path = f"/fr/tournoi/{slug}"
    pages = _edition_pages(db, t)
    up = [P._row(p) for p in pages if p.finished_at is None]
    dn = [P._row(p) for p in reversed(pages) if p.finished_at is not None]
    ok = sum(1 for p in pages if p.finished_at and str(p.result_winner_id) == str(p.snapshot.get("fav_id")))
    tot = sum(1 for p in pages if p.finished_at)
    crumbs = [("Accueil", "/"), ("Tournois", "/fr/tournois"), (t["name"], path)]
    h = _crumb_html(crumbs)
    h += f'<h1>Pronostics {html.escape(t["name"])} : matchs, probabilités et résultats</h1>'
    h += f'<div class="chips"><span class="chip">{html.escape(t["level"])}</span><span class="chip surf" style="--surf:var(--{t["surface"]})">{surf.capitalize()}</span><span class="chip">{html.escape(t["city"])}</span><span class="chip">{html.escape(t["when"])}</span></div>'
    h += R.CTA_HTML
    fmt = ("Chez les messieurs, les matchs se jouent au meilleur des 5 sets, ce qui avantage le joueur le plus complet : sur la durée, le favori est moins exposé à un coup de chaud." if t["bo5"]
           else "Les matchs se jouent au meilleur des 3 sets, un format où un seul set raté peut suffire à faire basculer un match.")
    fin = finals_section(pages)
    retro_html = retro_sections(db, slug)
    if up:
        h += '<section class="card"><h2>Prochains matchs et pronostics</h2>' + R._grouped(up) + '</section>'
    h += fin
    h += retro_html
    if dn:
        h += '<section class="card"><h2>Derniers résultats</h2>' + R._grouped(dn) + '</section>'
    if tot:
        h += f'<section class="card"><h2>Fiabilité sur ce tournoi</h2><div class="proj"><div><b>{R.fr(round(100*ok/tot,1))} %</b><small>pronostics justes</small></div><div><b>{ok}/{tot}</b><small>matchs vérifiés</small></div><div><a class="btn" href="/fr/bilan">Bilan public</a></div></div></section>'
    if not (up or dn or fin or retro_html):
        nxt = (db.query(models.MatchPage).filter(models.MatchPage.finished_at.is_(None), ~models.MatchPage.match_key.like("retro|%"),
                                                models.MatchPage.scheduled_time >= datetime.utcnow() - timedelta(hours=6))
               .order_by(models.MatchPage.scheduled_time).limit(10).all())
        h += (f'<section class="card"><p class="pend" style="margin:0">Aucun match de {html.escape(t["name"])} n\'est programmé pour le moment. '
              'Voici les prochains pronostics tennis, tournois ATP et WTA confondus.</p></section>')
        if nxt:
            h += '<section class="card"><h2>Prochains pronostics</h2>' + R._grouped([P._row(x) for x in nxt]) + '<p style="margin:14px 0 0"><a class="btn ghost" href="/fr/pronostics">Voir tous les pronostics</a></p></section>'
    fav = ''.join(_fav_table(db, t["surface"], tour, f"Favoris {'messieurs' if tour == 'atp' else 'dames'} selon TennisMind") for tour in t["tours"])
    if fav:
        h += f'<section class="card"><h2>Qui est le plus fort sur {surf} ?</h2><p class="pend" style="margin:0 0 6px">La note sur 100 mesure le niveau d\'un joueur sur {surf} selon TennisMind : plus elle est haute, plus il est redoutable sur cette surface. Elle est calculée sur ses résultats passés.</p>{fav}</section>'
    h += f'<section class="card analysis"><h2>Le tournoi en bref</h2><p>{html.escape(t["blurb"])}</p><p>{fmt}</p><p>TennisMind calcule pour chaque match une probabilité de victoire à partir du niveau de chaque joueur sur {surf}, de sa forme récente, du face-à-face et des conditions de jeu. Les pronostics sont publiés avant le match puis comparés au résultat réel.</p></section>'
    faq = [(f"Sur quelle surface se joue {t['name']} ?", f"{t['name']} se joue sur {surf}, à {t['city']}, généralement en {t['when']}."),
           (f"Comment TennisMind pronostique-t-il {t['name']} ?", f"Chaque match est évalué avec le niveau des joueurs sur {surf}, leur forme récente, leur historique face à face et la météo, puis comparé à l'historique des matchs ATP et WTA.")]
    h += '<section class="card"><h2>Questions fréquentes</h2>' + ''.join(f'<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in faq) + '</section>'
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": BASE + path, "url": BASE + path, "name": f"Pronostics {t['name']}", "inLanguage": "fr"},
        _crumbs(crumbs),
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    return R.page_shell(f"Pronostic {t['name']} : favoris et probabilités | TennisMind",
                        f"Pronostics {t['name']} : favoris sur {surf}, probabilité de victoire de chaque match, score probable et résultats réels. {t['level']}, {t['city']}.",
                        path, h, ld)


def render_tournois(db: Session) -> str:
    crumbs = [("Accueil", "/"), ("Tournois", "/fr/tournois")]
    h = _crumb_html(crumbs) + '<h1>Pronostics des grands tournois de tennis</h1>'
    h += '<p style="color:var(--ts);margin:0 0 22px">Grands Chelems et Masters 1000 : favoris, probabilités de victoire et résultats, mis à jour tout au long de la saison.</p>'
    for title, lvl in (("Grands Chelems", "Grand Chelem"), ("Masters 1000", None)):
        items = [(s, t) for s, t in T.items() if (t["level"] == "Grand Chelem") == (lvl is not None)]
        h += f'<section class="card"><h2>{title}</h2><div class="rel">' + ''.join(
            f'<a href="/fr/tournoi/{s}">{html.escape(t["name"])}<span>{SURF_LABEL[t["surface"]].capitalize()} · {html.escape(t["when"])}</span></a>' for s, t in items) + '</div></section>'
    eds = {}
    for slug, name, mod in db.query(models.MatchPage.tournament_slug, models.MatchPage.tournament_name, models.MatchPage.modified_at).all():
        if slug:
            eds[slug] = name
    if eds:
        h += '<section class="card"><h2>Tournois en cours ou récents</h2><div class="rel">' + ''.join(
            f'<a href="/fr/tournoi/{s}">{html.escape(n or s)}<span>Voir les matchs</span></a>' for s, n in sorted(eds.items())) + '</div></section>'
    return R.page_shell("Pronostics des grands tournois de tennis | TennisMind",
                        "Pronostics des Grands Chelems et Masters 1000 : favoris selon TennisMind, probabilités de victoire et résultats réels.",
                        "/fr/tournois", h, {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Tournois de tennis", "url": BASE + "/fr/tournois", "inLanguage": "fr"})


# ---------------------------------------------------------------- players --
def top_players(db: Session):
    return (db.query(models.Player)
            .filter(models.Player.current_rank.isnot(None), models.Player.current_rank <= MAX_PLAYER_RANK,
                    models.Player.data_confidence != models.DataConfidenceEnum.insufficient)
            .order_by(models.Player.current_rank).all())


def find_player(db: Session, slug: str):
    for p in top_players(db):
        if player_slug(p) == slug:
            return p
    return None


def render_joueurs(db: Session) -> str:
    crumbs = [("Accueil", "/"), ("Joueurs", "/fr/joueurs")]
    h = _crumb_html(crumbs) + '<h1>Pronostics par joueur : ATP et WTA</h1>'
    h += '<p style="color:var(--ts);margin:0 0 22px">Fiche de chaque joueur du top 100 : classement, niveau par surface, forme, prochains pronostics et derniers résultats.</p>'
    for tour, lab in (("atp", "Messieurs (ATP)"), ("wta", "Dames (WTA)")):
        ps = [p for p in top_players(db) if p.tour.value == tour]
        if ps:
            h += f'<section class="card"><h2>{lab}</h2><div class="rel">' + ''.join(
                f'<a href="/fr/joueur/{player_slug(p)}">{html.escape(p.name)}<span>N°{p.current_rank}</span></a>' for p in ps) + '</div></section>'
    return R.page_shell("Pronostics tennis par joueur : fiches ATP et WTA | TennisMind",
                        "Fiches des joueurs ATP et WTA : classement, niveau par surface, forme récente, prochains pronostics et résultats.",
                        "/fr/joueurs", h, {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Joueurs de tennis", "url": BASE + "/fr/joueurs", "inLanguage": "fr"})


def _player_photo(pages, pid):
    for pg in sorted(pages, key=lambda x: x.scheduled_time or datetime.min, reverse=True):
        s = pg.snapshot or {}
        img = s.get("img1") if str(pg.player1_id) == str(pid) else s.get("img2")
        if img and not img.startswith("data:"):
            return img
    return None


def render_player(db: Session, slug: str) -> Optional[str]:
    from app.services.prediction import _recent_form
    p = find_player(db, slug)
    if not p:
        return None
    path = f"/fr/joueur/{slug}"
    tour = _tour(p)
    pages = (db.query(models.MatchPage).filter(or_(models.MatchPage.player1_id == p.id, models.MatchPage.player2_id == p.id))
             .order_by(models.MatchPage.scheduled_time).all())
    up = [P._row(x) for x in pages if x.finished_at is None]
    dn = [P._row(x) for x in reversed(pages) if x.finished_at is not None]
    bio = P.player_bio(p)
    lv = {s: _elo_to_level_pct(getattr(p, f)) for s, f in SURF_FIELD.items()}
    best = max(lv, key=lambda s: lv[s] or 0)
    form = _recent_form(db, p.id)
    since = datetime.utcnow() - timedelta(days=365)
    season = P.record(db, p.id, since)
    tr = P.player_traits(db, p.id)
    photo = _player_photo(pages, p.id) or P.photo_map(db, [p.id]).get(str(p.id))
    crumbs = [("Accueil", "/"), ("Joueurs", "/fr/joueurs"), (p.name, path)]
    h = _crumb_html(crumbs) + f'<h1>Pronostic {html.escape(p.name)} : classement, forme et prochains matchs</h1>'
    chips = f'<span class="chip">{tour} · N°{p.current_rank}</span>'
    for k, fmt in (("pays", "{}"), ("age", "{} ans"), ("taille", "{} cm"), ("main", "{}")):
        if bio.get(k):
            chips += f'<span class="chip">{html.escape(fmt.format(bio[k]))}</span>'
    h += f'<div class="chips">{chips}</div>'
    h += R.CTA_HTML
    img = f'<img class="ph" src="{photo}" alt="{html.escape(p.name)}" width="112" height="140" referrerpolicy="no-referrer" style="margin:0 18px 0 0;float:left">' if photo else ''
    para = f"{html.escape(p.name)} est actuellement n°{p.current_rank} au classement {tour}. Selon TennisMind, sa meilleure surface est le {SURF_LABEL[best]} (niveau {lv[best]} sur 100), contre "
    para += " et ".join(f"{lv[s]} sur 100 sur {SURF_LABEL[s]}" for s in lv if s != best) + "."
    if season:
        para += f" Sur les 12 derniers mois, son bilan est de {season[0]} victoire{'s' if season[0] > 1 else ''} pour {season[1]} défaite{'s' if season[1] > 1 else ''}."
    if form:
        para += f" Forme récente : {form['wins']} victoire{'s' if form['wins'] > 1 else ''} sur ses {len(form['results'])} derniers matchs."
    if tr:
        para += f" Il compte en moyenne {str(tr['ace']).replace('.', ',')} aces par match et gagne {tr['ret']} % des points au retour." if tour == "ATP" else f" Elle compte en moyenne {str(tr['ace']).replace('.', ',')} aces par match et gagne {tr['ret']} % des points au retour."
    paras = [para]
    if getattr(p, "playing_style", None):
        paras.append(html.escape(p.playing_style))
    if up:
        s = pages[[x.slug for x in pages].index(up[0]["slug"])].snapshot
        opp = s["p2"] if str(pages[[x.slug for x in pages].index(up[0]["slug"])].player1_id) == str(p.id) else s["p1"]
        paras.append(f"Prochain match : contre {html.escape(opp)} ({html.escape(up[0]['tournoi'])}, {html.escape(up[0]['day'])}). Probabilités et score probable sur la page du match.")
    h += f'<section class="card analysis"><h2>Profil de {html.escape(p.name)}</h2>{img}' + ''.join(f'<p>{x if i == 0 else x}</p>' for i, x in enumerate(paras)) + '<div style="clear:both"></div></section>'
    rows = ''.join(f'<div class="fr"><span>{SURF_LABEL[s].capitalize()}</span><i style="width:{lv[s]}%"></i><b style="margin-left:8px">{lv[s]}</b></div>' for s in ("hard", "clay", "grass") if lv[s] is not None)
    h += f'<section class="card"><h2>Niveau TennisMind par surface</h2><div class="fac" style="margin-top:0">{rows}</div></section>'
    if up:
        h += f'<section class="card"><h2>Prochains pronostics de {html.escape(p.name)}</h2>' + R._grouped(up) + '</section>'
    if dn:
        h += f'<section class="card"><h2>Derniers résultats</h2>' + R._grouped(dn) + '</section>'
    faq = [(f"Quel est le classement de {p.name} ?", f"{p.name} est n°{p.current_rank} au classement {tour}."),
           (f"Sur quelle surface {p.name} est-il le plus à l'aise ?", f"D'après le niveau TennisMind, sa meilleure surface est le {SURF_LABEL[best]}.")]
    h += '<section class="card"><h2>Questions fréquentes</h2>' + ''.join(f'<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in faq) + '</section>'
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "ProfilePage", "@id": BASE + path, "url": BASE + path, "name": f"Pronostic {p.name}", "inLanguage": "fr",
         "mainEntity": {"@type": "Person", "name": p.name, "jobTitle": "Joueur de tennis professionnel"}},
        _crumbs(crumbs),
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    return R.page_shell(f"Pronostic {p.name} : classement, forme et prochains matchs | TennisMind",
                        f"{p.name} (n°{p.current_rank} {tour}) : niveau par surface, forme récente, prochains pronostics et résultats réels.",
                        path, h, ld)


# ------------------------------------------------------------ daily pages --
def render_day(db: Session, when: str) -> Optional[str]:
    if when not in ("aujourdhui", "demain"):
        return None
    now = datetime.now(P.PARIS)
    day = (now if when == "aujourdhui" else now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    lo = day.astimezone(timezone.utc).replace(tzinfo=None)
    pages = (db.query(models.MatchPage).filter(models.MatchPage.scheduled_time >= lo, models.MatchPage.scheduled_time < lo + timedelta(days=1))
             .order_by(models.MatchPage.scheduled_time).all())
    label = P.fr_date_long(day)
    word = "aujourd'hui" if when == "aujourdhui" else "demain"
    path = f"/fr/pronostics/{when}"
    crumbs = [("Accueil", "/"), ("Pronostics", "/fr/pronostics"), (word.capitalize(), path)]
    h = _crumb_html(crumbs) + f'<h1>Pronostics tennis {word} : {label}</h1>'
    h += R.CTA_HTML
    if pages:
        h += '<section class="card"><h2>Matchs du jour</h2>' + R._grouped([P._row(x) for x in pages]) + '</section>'
    else:
        h += '<section class="card"><p class="pend">Aucun pronostic publié pour ce jour pour le moment. <a href="/fr/pronostics">Voir tous les pronostics</a>.</p></section>'
    return R.page_shell(f"Pronostics tennis {word} ({label}) | TennisMind",
                        f"Pronostics tennis {word}, {label} : probabilité de victoire et score probable de chaque match ATP et WTA.",
                        path, h, None, "index,follow" if pages else "noindex,follow")


# ---------------------------------------------------------------- sitemap --
def sitemap_entries(db: Session):
    today = datetime.utcnow().date().isoformat()
    e = [("/fr/tournois", today, "daily"), ("/fr/joueurs", today, "daily"),
         ("/fr/pronostics/aujourdhui", today, "hourly"), ("/fr/pronostics/demain", today, "hourly")]
    e += [(f"/fr/tournoi/{s}", today, "daily") for s in T]
    e += [(f"/fr/joueur/{player_slug(p)}", today, "daily") for p in top_players(db)]
    return e

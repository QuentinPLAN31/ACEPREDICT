# A lancer via railway ssh: PYTHONPATH=/app python3 -m scripts.check_draw_structure
#
# fetch_draw() (app/services/scrape_provider.py) regroupe les divs du
# tableau par decalage 'left' (colonne = tour). On a corrige le calcul du
# round pour le deduire de la taille de la 1ere colonne, mais ca n'a rien
# change en pratique (R128 reste a 70 au lieu de 64 attendu) -- ce script
# affiche la structure REELLE (nombre de colonnes, taille de chacune, et un
# extrait de son contenu) pour comprendre pourquoi.
import asyncio

from app.services import scrape_provider as sp


async def main():
    html = await sp._get(f"{sp.BASE_URL}/us-open/2026/atp-men/")
    if not html:
        print("HTML introuvable (echec requete).")
        return
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    draw_div = soup.find(id="draw")
    if not draw_div:
        print("Aucun div id='draw' trouve sur la page.")
        return

    entries = []
    for div in draw_div.find_all("div", recursive=False):
        left = sp._extract_px(div.get("style", ""), "left")
        top = sp._extract_px(div.get("style", ""), "top")
        text = div.get_text(strip=True)
        if left is None or top is None:
            continue
        if text[:1].isdigit():
            continue
        entries.append((left, top, text))

    columns: dict[int, list[tuple[int, str]]] = {}
    for left, top, text in entries:
        columns.setdefault(left, []).append((top, text))

    print(f"{len(columns)} colonne(s) (valeurs 'left' distinctes) trouvee(s) :")
    for left in sorted(columns.keys()):
        items = sorted(columns[left], key=lambda x: x[0])
        slots = [(top, sp._clean_draw_name(text)) for top, text in items if top != 0]
        non_empty = [s for s in slots if s[1]]
        print(f"  left={left}px : {len(items)} div(s) brut(s), {len(slots)} slot(s) (top!=0), {len(non_empty)} non-vide(s)")
        print(f"    exemples: {[s[1] for s in slots[:6]]}")


asyncio.run(main())

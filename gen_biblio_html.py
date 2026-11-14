#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_biblio_html.py — Bibliographie Zotero/BetterBibLaTeX -> page HTML.

Reproduit la logique de bibliographie.tex du projet Overleaf :
  * memes categories et codes : TH, ACL, PP, ACLN, OS, COM, INV, PRE, RR, BP, ENC
  * tri ynt (annee croissante, auteur, titre)
  * nom du chercheur mis en evidence (classe CSS "me")
  * liens HAL / Zenodo (champ Zotero "extra" : tex.annotation: HAL: hal-xxxx)
    et DOI, sous forme de badges cliquables
  * options --start-year / --end-year : publications hors periode grisees,
    comme le grayout du preambule LaTeX

Utilisation :
    pip install "bibtexparser==1.4.1" pylatexenc
    python gen_biblio_html.py Publications_ALH_BetterBibLaTex.bib -o index.html
    python gen_biblio_html.py mon.bib -o index.html --start-year 2023 --end-year 2026
"""

import argparse
import html
import re
import sys
from datetime import date

try:
    import bibtexparser
    from pylatexenc.latex2text import LatexNodes2Text
except ImportError:
    sys.exit('Dependances manquantes : pip install "bibtexparser==1.4.1" pylatexenc')

L2T = LatexNodes2Text()

# ---------------------------------------------------------------------------
# Configuration : adapter ces valeurs a votre situation
# ---------------------------------------------------------------------------
FAMILLE_CHERCHEUR = "l'hostis"   # nom de famille a mettre en evidence
PREFIX_CHERCHEUR = "l'"          # cas "family=Hostis, prefix=l'" (BetterBibLaTeX)
LIEN_HAL = "https://hal.science/"
LIEN_ZENODO = "https://zenodo.org/records/"
LIEN_DOI = "https://doi.org/"

CATEGORIES = [
    # (code affiche, ancre html, titre de section)
    ("TH",    "theses",         "Thèses et HDR"),
    ("ACL",   "articles",       "Articles dans des revues à comité de lecture"),
    ("PP",    "preprints",      "Preprints"),
    ("ACLN",  "articles-nopr",  "Articles sans comité de lecture"),
    ("OS",    "chapitres",      "Chapitres d’ouvrages"),
    ("COM",   "communications", "Communications avec actes"),
    ("INV",   "invitations",    "Conférences et séminaires sur invitation"),
    ("PRE",   "presentations",  "Présentations"),
    ("RR",    "rapports",       "Rapports de recherche"),
    ("BP",    "blog",           "Billets de blog scientifique"),
    ("ENC",   "encadrements",   "Thèses et mémoires encadrés"),
    ("AUT",   "autres",         "Autres productions"),
]

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# ---------------------------------------------------------------------------
# Analyse du .bib
# ---------------------------------------------------------------------------
def norm(s):
    """Normalise apostrophes typographiques et casse pour comparaisons."""
    return s.replace("\u2019", "'").replace("\u02bc", "'").lower().strip()


def est_chercheur(famille, prefixe=""):
    f = norm(famille)
    p = norm(prefixe)
    if f in (FAMILLE_CHERCHEUR, "lhostis", FAMILLE_CHERCHEUR.replace("'", "")):
        return True
    # BetterBibLaTeX peut écrire : family=Hostis, given=Alain, prefix=l'
    return f == FAMILLE_CHERCHEUR.split("'")[-1] and p.startswith(FAMILLE_CHERCHEUR.split("'")[0] + "'")


def split_auteurs(champ):
    """Coupe le champ author sur ' and ' au niveau supérieur (hors accolades)."""
    res, profondeur, debut, i = [], 0, 0, 0
    champ = champ or ""
    while i < len(champ):
        c = champ[i]
        if c == "{":
            profondeur += 1
        elif c == "}":
            profondeur -= 1
        if profondeur == 0 and champ[i:i + 5].lower() == " and ":
            res.append(champ[debut:i])
            debut = i + 5
            i += 5
        else:
            i += 1
    res.append(champ[debut:])
    return [a.strip() for a in res if a.strip()]


RE_FAMILY = re.compile(r"family\s*=\s*([^,]+)")
RE_GIVEN = re.compile(r"given\s*=\s*([^,]+)")
RE_PREFIX = re.compile(r"prefix\s*=\s*([^,]+)")


def parse_auteur(brut):
    """Retourne (famille, prefixe, affichage) pour un auteur."""
    brut = brut.strip()
    m = RE_FAMILY.search(brut)
    if m:
        famille = m.group(1).strip()
        g = RE_GIVEN.search(brut)
        prenom = g.group(1).strip() if g else ""
        p = RE_PREFIX.search(brut)
        prefixe = p.group(1).strip() if p else ""
        affichage = prefixe + famille + (", " + prenom if prenom else "")
        return famille, prefixe, affichage
    if "," in brut:
        famille, prenom = brut.split(",", 1)
        return famille.strip(), "", famille.strip() + ", " + prenom.strip()
    morceaux = brut.split()
    if len(morceaux) > 1:
        famille = morceaux[-1]
        prenom = " ".join(morceaux[:-1])
        return famille, "", famille + ", " + prenom
    return brut, "", brut


def latex_vers_unicode(s):
    if not s:
        return ""
    try:
        s = L2T.latex_to_text(s)
    except Exception:
        pass
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def pages_propres(p):
    return (p or "").replace("--", "–").strip()


def annee_notice(e):
    for champ in ("date", "year"):
        m = re.search(r"(\d{4})", e.get(champ, "") or "")
        if m:
            return int(m.group(1))
    return 0


def mots_cles(e):
    return {k.strip().lower() for k in (e.get("keywords", "") or "").split(",") if k.strip()}


def classifier(e):
    """Meme logique que les \\printbibliography de bibliographie.tex."""
    t = e["ENTRY_TYPE"].lower()
    kw = mots_cles(e)
    if t == "thesis":
        return "ENC" if "enc" in kw else "TH"
    if t == "article":
        return "ACLN" if "nopr" in kw else "ACL"
    if t == "unpublished":
        if "presentation" in kw:
            return "INV" if "invited" in kw else "PRE"
        return "PP"
    if t == "incollection":
        return "OS"
    if t == "inproceedings":
        return "COM"
    if t == "report":
        return "RR"
    if t == "online":
        return "BP"
    return "AUT"   # book, inbook, misc, artwork... : section "Autres"


RE_HAL_ANN = re.compile(r"hal\s*:\s*([a-z][a-z0-9]*[-_][0-9a-z\-_]+)", re.I)
RE_HAL_URL = re.compile(r"(?:hal\.science|hal\.fr)/((?:hal|tel|halshs|mem|medihal)-[0-9a-z\-_]+)", re.I)
RE_ZENODO_ANN = re.compile(r"zenodo\s*:?\s*([0-9]+)", re.I)
RE_ZENODO_URL = re.compile(r"zenodo\.org/records/([0-9]+)", re.I)


def liens_notice(e):
    """Retourne une liste [(etiquette, url)] pour HAL, Zenodo et DOI."""
    liens = []
    hal_id = None
    for champ in ("annotation", "note"):
        m = RE_HAL_ANN.search(e.get(champ, "") or "")
        if m:
            hal_id = m.group(1)
            break
    if not hal_id:
        m = RE_HAL_URL.search(e.get("url", "") or "")
        if m:
            hal_id = m.group(1)
    if hal_id:
        liens.append(("HAL", LIEN_HAL + hal_id))

    zenodo_id = None
    for champ in ("annotation", "note"):
        m = RE_ZENODO_ANN.search(e.get(champ, "") or "")
        if m:
            zenodo_id = m.group(1)
            break
    if not zenodo_id:
        m = RE_ZENODO_URL.search(e.get("url", "") or "")
        if m:
            zenodo_id = m.group(1)
    if zenodo_id:
        liens.append(("Zenodo", LIEN_ZENODO + zenodo_id))

    doi = (e.get("doi", "") or "").strip().rstrip(".")
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    if doi:
        liens.append(("DOI", LIEN_DOI + doi))
    return liens


def references_auteurs(e):
    """HTML des auteurs, nom du chercheur mis en evidence."""
    bouts = []
    for brut in split_auteurs(e.get("author", "")):
        famille, prefixe, affichage = parse_auteur(brut)
        affichage = latex_vers_unicode(affichage)
        if est_chercheur(famille, prefixe):
            affichage = '<span class="me">' + html.escape(affichage) + "</span>"
        else:
            affichage = html.escape(affichage)
        bouts.append(affichage)
    if not bouts:
        return ""
    if len(bouts) == 1:
        return bouts[0]
    return ", ".join(bouts[:-1]) + " et " + bouts[-1]


def venue(e):
    """Description bibliographique selon le type de notice."""
    t = e["ENTRY_TYPE"].lower()
    g = lambda f: latex_vers_unicode(e.get(f, "") or "")
    if t == "article":
        bits = []
        if g("journaltitle"):
            bits.append("<em>" + html.escape(g("journaltitle")) + "</em>")
        if e.get("volume"):
            bits.append("vol. " + html.escape(str(e["volume"])))
        if e.get("number"):
            bits.append("n° " + html.escape(str(e["number"])))
        if e.get("pages"):
            bits.append("p. " + html.escape(pages_propres(e["pages"])))
        return ", ".join(bits)
    if t in ("incollection", "inbook"):
        bits = []
        if g("booktitle"):
            bits.append("in <em>" + html.escape(g("booktitle")) + "</em>")
        if e.get("pages"):
            bits.append("p. " + html.escape(pages_propres(e["pages"])))
        if g("publisher"):
            bits.append(html.escape(g("publisher")))
        return ", ".join(bits)
    if t == "inproceedings":
        bits = []
        if g("booktitle"):
            bits.append("in <em>" + html.escape(g("booktitle")) + "</em>")
        if g("location"):
            bits.append(html.escape(g("location")))
        if g("publisher"):
            bits.append(html.escape(g("publisher")))
        if e.get("pages"):
            bits.append("p. " + html.escape(pages_propres(e["pages"])))
        return ", ".join(bits)
    if t == "thesis":
        bits = []
        if g("type"):
            bits.append(html.escape(g("type")))
        if g("institution"):
            bits.append(html.escape(g("institution")))
        if e.get("pagetotal"):
            bits.append(html.escape(str(e["pagetotal"])) + " p.")
        return ", ".join(bits)
    if t == "unpublished":
        bits = []
        if g("eventtitle"):
            bits.append(html.escape(g("eventtitle")))
        if g("venue"):
            bits.append(html.escape(g("venue")))
        return ", ".join(bits)
    if t == "report":
        bits = []
        if g("institution"):
            bits.append(html.escape(g("institution")))
        if g("type"):
            bits.append(html.escape(g("type")))
        return ", ".join(bits)
    if t == "online":
        return html.escape(g("journaltitle") or (e.get("url", "") or ""))
    return ""


# ---------------------------------------------------------------------------
# Génération HTML
# ---------------------------------------------------------------------------
CSS = """
:root { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        color: #1f2937; background: #f8fafc; line-height: 1.5; }
body { max-width: 900px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
header h1 { font-size: 1.6rem; margin-bottom: 0.2rem; }
.meta { color: #6b7280; font-size: 0.85rem; margin-bottom: 1rem; }
nav { position: sticky; top: 0; background: #f8fafc; padding: 0.5rem 0;
      border-bottom: 1px solid #e5e7eb; margin-bottom: 1.5rem; z-index: 10; }
nav a { display: inline-block; margin: 0.15rem 0.35rem 0.15rem 0; padding: 0.15rem 0.6rem;
        background: #eef2ff; color: #3730a3; border-radius: 999px;
        font-size: 0.78rem; text-decoration: none; }
nav a small { color: #6366f1; }
section h2 { font-size: 1.15rem; border-bottom: 2px solid #c7d2fe;
             padding-bottom: 0.25rem; margin-top: 2.2rem; }
ol { list-style: none; padding-left: 0; }
li { padding: 0.45rem 0; border-bottom: 1px dotted #e5e7eb; }
.code { display: inline-block; min-width: 4.2em; font-family: ui-monospace, monospace;
        font-size: 0.78rem; color: #374151; background: #f3f4f6;
        border-radius: 4px; padding: 0 0.35rem; margin-right: 0.35rem; }
.me { font-weight: 600; color: #0a7d33; }
em.journal { font-style: italic; }
.badge { display: inline-block; margin-left: 0.3rem; padding: 0.05rem 0.55rem;
         border-radius: 999px; font-size: 0.72rem; text-decoration: none;
         font-weight: 600; }
.hal { background: #fff1e5; color: #b45309; border: 1px solid #fdba74; }
.zenodo { background: #eff6ff; color: #1d4ed8; border: 1px solid #93c5fd; }
.doi { background: #f0fdf4; color: #15803d; border: 1px solid #86efac; }
.hors-periode { opacity: 0.45; }
footer { margin-top: 3rem; color: #9ca3af; font-size: 0.78rem; }
"""


def notice_html(code, numero, e, hors_periode):
    auteurs = references_auteurs(e)
    annee = annee_notice(e)
    titre = latex_vers_unicode(e.get("title", ""))
    v = venue(e)
    classe = "hors-periode" if hors_periode else ""
    badges = "".join(
        '<a class="badge %s" href="%s" target="_blank">%s</a>'
        % (lab.lower(), html.escape(url, quote=True), lab)
        for lab, url in liens_notice(e)
    )
    ref = "%s. %d. <em>%s</em>." % (auteurs, annee, html.escape(titre))
    if v:
        ref += " " + v + "."
    return ('<li class="%s"><span class="code">%s%d</span>%s%s</li>'
            % (classe, code, numero, ref, badges))


def construire_page(entrees, titre_page, debut, fin):
    par_cat = {code: [] for code, _, _ in CATEGORIES}
    for e in entrees:
        par_cat[classifier(e)].append(e)

    for code in par_cat:
        par_cat[code].sort(key=lambda e: (annee_notice(e),
                                          norm(e.get("author", "zzz")),
                                          latex_vers_unicode(e.get("title", "")).lower()))

    aujourdhui = date.today()
    date_fr = "%d %s %d" % (aujourdhui.day, MOIS_FR[aujourdhui.month - 1], aujourdhui.year)

    def dans_periode(e):
        a = annee_notice(e)
        return (debut is None or a >= debut) and (fin is None or a <= fin)

    total_periode = sum(1 for e in entrees if dans_periode(e))

    nav = []
    sections = []
    for code, ancre, titre_section in CATEGORIES:
        liste = par_cat[code]
        if not liste:
            continue
        np = sum(1 for e in liste if dans_periode(e))
        nav.append('<a href="#%s">%s <small>(%d/%d)</small></a>'
                   % (ancre, code, np, len(liste)))
        items = []
        for i, e in enumerate(liste, start=1):
            items.append(notice_html(code, i, e, not dans_periode(e)))
        sections.append('<section id="%s"><h2>%s <small>(%d publications '
                        'dans la période)</small></h2><ol>%s</ol></section>'
                        % (ancre, titre_section, np, "".join(items)))

    page = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITRE@@</title>
<style>@@CSS@@</style>
</head>
<body>
<header>
<h1>@@TITRE@@</h1>
<p class="meta">@@META@@</p>
</header>
<nav>@@NAV@@</nav>
@@SECTIONS@@
<footer>Page générée automatiquement à partir du fichier .bib
(Zotero &ndash; Better BibLaTeX). Dernière mise à jour : @@DATE@@.</footer>
</body>
</html>
"""
    meta = ("%d notices au total, %d dans la période%s."
            % (len(entrees), total_periode,
               " %d&ndash;%d" % (debut, fin) if debut else ""))
    page = (page.replace("@@TITRE@@", html.escape(titre_page))
                .replace("@@CSS@@", CSS)
                .replace("@@META@@", meta)
                .replace("@@NAV@@", "".join(nav))
                .replace("@@SECTIONS@@", "\n".join(sections))
                .replace("@@DATE@@", date_fr))
    return page


def main():
    p = argparse.ArgumentParser(description="Bibliographie .bib -> page HTML")
    p.add_argument("bib", help="fichier .bib exporté par Better BibLaTeX")
    p.add_argument("-o", "--output", default="index.html", help="fichier HTML de sortie")
    p.add_argument("--titre", default="Publications", help="titre de la page")
    p.add_argument("--start-year", type=int, default=None,
                   help="début de la période (les publications antérieures sont grisées)")
    p.add_argument("--end-year", type=int, default=None,
                   help="fin de la période")
    args = p.parse_args()

    with open(args.bib, encoding="utf-8") as f:
        base = bibtexparser.load(f)
    entrees = [e for e in base.entries if e.get("author") or e.get("editor")]

    page = construire_page(entrees, args.titre, args.start_year, args.end_year)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(page)
    print("OK : %d notices -> %s" % (len(entrees), args.output))


if __name__ == "__main__":
    main()

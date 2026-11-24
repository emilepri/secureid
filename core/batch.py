"""Émission en masse à partir d'un fichier CSV ou Excel et d'un dossier de photos.

Colonnes reconnues (l'ordre et les accents/majuscules n'ont pas d'importance) :
    nom, prenom, date_naissance, statut, fonction, service, photo, profil, validite_mois
- date_naissance : JJ/MM/AAAA ou AAAA-MM-JJ (ou une vraie date Excel)
- photo : nom du fichier dans le dossier de photos (ex. diop_awa.jpg)
- profil, validite_mois : facultatifs, sinon on prend les valeurs choisies dans l'interface

Toutes les lignes sont contrôlées AVANT la première émission : l'opérateur voit
les erreurs ligne par ligne et décide d'émettre seulement les lignes valides.
"""

import csv
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from core.issuer_service import CardRequest, IssuerService, ValidationError, validate

COLUMNS = ["nom", "prenom", "date_naissance", "statut", "fonction", "service", "photo", "profil", "validite_mois"]
ALIASES = {
    "prenoms": "prenom", "naissance": "date_naissance", "date_de_naissance": "date_naissance", "ne_le": "date_naissance",
    "role": "statut", "poste": "fonction", "departement": "service", "photo_fichier": "photo", "fichier_photo": "photo",
    "validite": "validite_mois", "type": "profil",
}
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MAX_ROWS = 2000


class BatchFileError(ValueError):
    pass


class _Semicolon(csv.excel):
    delimiter = ";"  # séparateur par défaut d'Excel en français


@dataclass
class BatchLine:
    line: int                       # numéro de ligne dans le fichier (en-tête = 1)
    raw: dict
    request: CardRequest | None = None
    error: str = ""
    card_id: str = ""               # rempli après émission

    @property
    def ok(self) -> bool:
        return self.request is not None and not self.error


@dataclass
class BatchReport:
    lines: list[BatchLine] = field(default_factory=list)

    @property
    def valid(self) -> list[BatchLine]:
        return [ln for ln in self.lines if ln.ok]

    @property
    def invalid(self) -> list[BatchLine]:
        return [ln for ln in self.lines if not ln.ok]


def _key(header: str) -> str:
    k = unicodedata.normalize("NFKD", str(header)).encode("ascii", "ignore").decode().strip().lower()
    k = "_".join(k.replace("-", " ").replace("'", " ").split())
    return ALIASES.get(k, k)


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"date de naissance « {text} » non reconnue (format JJ/MM/AAAA attendu)")


def read_rows(path: str | Path) -> list[tuple[int, dict]]:
    """Lit un .csv (séparateur ; ou , détecté) ou un .xlsx. Retourne [(n° de ligne, {colonne: valeur})]."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
    elif path.suffix.lower() == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,\t")
        except (csv.Error, IndexError):
            dialect = _Semicolon
        rows = list(csv.reader(text.splitlines(), dialect))
    else:
        raise BatchFileError("Format non pris en charge : utilise un fichier .csv ou .xlsx.")

    if not rows:
        raise BatchFileError("Le fichier est vide.")
    headers = [_key(h) for h in rows[0]]
    missing = {"nom", "prenom", "date_naissance", "photo"} - set(headers)
    if missing:
        raise BatchFileError("Colonnes obligatoires absentes : " + ", ".join(sorted(missing)))
    data = []
    for n, row in enumerate(rows[1:], start=2):
        values = {h: ("" if v is None else v) for h, v in zip(headers, row)}
        if not any(str(v).strip() for v in values.values()):
            continue  # ligne vide
        data.append((n, values))
    if len(data) > MAX_ROWS:
        raise BatchFileError(f"Trop de lignes ({len(data)}) : {MAX_ROWS} au maximum par fichier.")
    return data


def _find_photo(photos_dir: Path, name: str) -> Path:
    name = str(name).strip()
    if not name:
        raise ValidationError("photo non renseignée")
    # Un simple nom de fichier, sans chemin : empêche de lire hors du dossier (ex. « ..\\..\\secret.png »)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise ValidationError(f"nom de photo refusé : « {name} » (indique seulement le nom du fichier)")
    candidate = photos_dir / name
    if candidate.suffix.lower() not in PHOTO_EXT:
        for ext in PHOTO_EXT:
            if candidate.with_suffix(ext).exists():
                return candidate.with_suffix(ext)
    if not candidate.exists():
        raise ValidationError(f"photo « {name} » introuvable dans le dossier")
    return candidate


def analyse(path: str | Path, photos_dir: str | Path, default_profil: str = "ecole",
            default_validite: int = 12, modele: str = "officiel") -> BatchReport:
    photos_dir = Path(photos_dir)
    report = BatchReport()
    seen = set()
    for n, raw in read_rows(path):
        line = BatchLine(n, raw)
        report.lines.append(line)
        try:
            profil = _key(raw.get("profil") or default_profil)
            profil = {"etudiant": "ecole", "eleve": "ecole", "employe": "entreprise"}.get(profil, profil)
            validite = int(float(raw.get("validite_mois") or default_validite))
            statut = str(raw.get("statut") or ("Employé(e)" if profil == "entreprise" else "Étudiant(e)")).strip()
            req = CardRequest(profil=profil, nom=str(raw.get("nom", "")).strip(), prenom=str(raw.get("prenom", "")).strip(),
                              naiss=_parse_date(raw.get("date_naissance")), role=statut, validite_mois=validite,
                              fonction=str(raw.get("fonction", "")).strip(), service=str(raw.get("service", "")).strip(),
                              modele=modele, photo_source=_find_photo(photos_dir, raw.get("photo", "")))
            validate(req)
            ident = (req.nom.upper(), req.prenom.lower(), req.naiss)
            if ident in seen:
                raise ValidationError("doublon : même nom, prénom et date de naissance qu'une ligne précédente")
            seen.add(ident)
            line.request = req
        except (ValidationError, ValueError) as exc:
            line.error = str(exc).replace("\n", " ; ")
    return report


def issue_valid(service: IssuerService, report: BatchReport, on_progress=None):
    """Émet les lignes valides. Retourne [(BatchLine, recto, verso)] pour les planches d'impression."""
    issued = []
    for i, line in enumerate(report.valid, start=1):
        try:
            card, recto, verso = service.issue_with_faces(line.request)
        except Exception as exc:  # une ligne en échec n'arrête pas le lot
            line.error = f"émission impossible : {exc}"
            continue
        line.card_id = card.card_id
        issued.append((line, recto, verso))
        if on_progress:
            on_progress(i, len(report.valid))
    return issued


def write_report(report: BatchReport, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ligne", "nom", "prenom", "resultat", "n_carte", "detail"])
        for ln in report.lines:
            w.writerow([ln.line, ln.raw.get("nom", ""), ln.raw.get("prenom", ""),
                        "EMISE" if ln.card_id else ("ERREUR" if ln.error else "NON EMISE"), ln.card_id, ln.error])
    return path


def write_template(path: str | Path) -> Path:
    """Fichier modèle à remplir (s'ouvre directement dans Excel)."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        w.writerow(["DIOP", "Awa", "15/01/2003", "Étudiante", "", "", "diop_awa.jpg", "ecole", "12"])
        w.writerow(["SALL", "Fatou", "02/06/1994", "Employée", "Analyste cybersécurité", "Sécurité des SI",
                    "sall_fatou.jpg", "entreprise", "24"])
    return path

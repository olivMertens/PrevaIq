"""Generate the PrevaIQ policy PDFs (conditions générales) indexed by the RAG.

Fictitious, original documents whose structure mirrors a French insurer's
conditions générales: Habitation, Auto, Flotte auto and Complémentaire santé.
Article numbers, deductibles and limits match the PrevaIQ demo data
(scripts/seed_data, scripts/generate_demo_*.py, prompts/*-claims-policies.json).

Usage:
    python scripts/generate_policy_pdfs.py            # writes assets/pdf/prevaiq/*.pdf
    python scripts/index_pdf_policies.py --dir assets/pdf/prevaiq --force
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _brand_config import get_brand  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BRAND = get_brand("prevaiq")
OUT_DIR = ROOT / "assets" / "pdf" / BRAND.name.lower()
COMPANY = f"{BRAND.name} Assurance"
LEGAL = (
    f"{COMPANY} — société d'assurance fictive créée pour démonstration. "
    "Document sans valeur contractuelle."
)
EDITION = "Édition 01/2026"

# No CSS backgrounds: MuPDF Story redraws earlier pages' backgrounds as stray bars.
CSS = f"""
* {{ font-family: sans-serif; }}
body {{ font-size: 9.5pt; line-height: 1.35; color: #1f2933; }}
h1 {{ font-size: 15pt; color: {BRAND.color_hex}; margin: 0 0 6pt 0; }}
h2 {{ font-size: 12pt; color: {BRAND.color_hex}; border-bottom: 1.5pt solid #2EC4B6;
      padding: 0 0 2pt 0; margin: 14pt 0 6pt 0; }}
h3 {{ font-size: 10pt; color: {BRAND.color_hex}; margin: 8pt 0 3pt 0; }}
p {{ margin: 0 0 4pt 0; text-align: justify; }}
ul {{ margin: 0 0 4pt 0; }}
li {{ margin: 0 0 1pt 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }}
th {{ color: {BRAND.color_hex}; font-size: 8.5pt; padding: 2pt 4pt;
      border: 0.5pt solid #2EC4B6; border-bottom: 1.5pt solid #2EC4B6; text-align: left; }}
td {{ font-size: 8.5pt; padding: 2pt 4pt; border: 0.5pt solid #9aa5b1; }}
.box {{ border: 0.8pt solid #2EC4B6; padding: 4pt 6pt; margin: 4pt 0 6pt 0; }}
.excl {{ border-left: 2.5pt solid #c0392b; padding: 2pt 6pt; margin: 4pt 0 6pt 0; }}
.def b {{ color: {BRAND.color_hex}; }}
"""


def art(num: str, title: str, body: str) -> str:
    return f"<h3>Article {num} — {title}</h3>{body}"


def section(title: str, body: str) -> str:
    return f"<h2>{title}</h2>{body}"


def excl(items: list[str], intro: str = "Sont exclus :") -> str:
    lis = "".join(f"<li>{i}</li>" for i in items)
    return f'<div class="excl"><p><b>{intro}</b></p><ul>{lis}</ul></div>'


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def defs(items: list[tuple[str, str]]) -> str:
    return "".join(f'<p class="def"><b>{k.upper()} :</b> {v}</p>' for k, v in items)


def common_provisions(first: int, sinistre_extra: str = "") -> str:
    """Contract life + miscellaneous provisions shared by every document."""
    n, m = first, first + 1
    return section(
        f"{n}. LA VIE DE VOTRE CONTRAT",
        art(f"{n}.1", "Formation, prise d'effet et durée",
            "<p>Le contrat est formé dès notre accord sur votre demande de souscription. Il prend "
            "effet à la date indiquée aux conditions particulières, pour une durée d'un an, et se "
            "renouvelle ensuite par tacite reconduction d'année en année, sauf résiliation.</p>")
        + art(f"{n}.2", "Vos déclarations",
              "<p>Le contrat est établi d'après vos réponses aux questions que nous vous posons. "
              "Vous devez déclarer en cours de contrat, dans les 15 jours où vous en avez "
              "connaissance, toute circonstance nouvelle qui aggrave le risque ou en crée de "
              "nouveaux (article L.113-2 du Code des assurances).</p>")
        + art(f"{n}.3", "Sanctions des fausses déclarations",
              "<p>Toute réticence ou fausse déclaration intentionnelle entraîne la nullité du "
              "contrat (article L.113-8). Une omission ou inexactitude non intentionnelle entraîne, "
              "selon le moment où elle est constatée, une augmentation de cotisation, la "
              "résiliation du contrat ou une réduction proportionnelle de l'indemnité "
              "(article L.113-9).</p>")
        + art(f"{n}.4", "Cotisation",
              "<p>La cotisation est payable d'avance, annuellement ou selon le fractionnement "
              "convenu. À défaut de paiement dans les 10 jours de l'échéance, nous pouvons, par "
              "lettre de mise en demeure, suspendre les garanties 30 jours après son envoi puis "
              "résilier le contrat 10 jours plus tard (article L.113-3).</p>")
        + art(f"{n}.5", "Résiliation",
              "<p>Vous pouvez résilier le contrat à l'échéance annuelle avec un préavis de deux "
              "mois, puis à tout moment après la première année (article L.113-15-2), ainsi que "
              "dans les cas prévus par la loi (changement de situation, vente du bien, "
              "augmentation de cotisation). Nous pouvons résilier après sinistre, pour non-paiement "
              "ou pour aggravation du risque, dans les conditions légales.</p>"),
    ) + section(
        f"{m}. DISPOSITIONS DIVERSES",
        art(f"{m}.1", "Prescription",
            "<p>Toute action dérivant du contrat est prescrite par deux ans à compter de "
            "l'événement qui y donne naissance (articles L.114-1 à L.114-3), délai interrompu par "
            "une des causes ordinaires d'interruption, la désignation d'un expert ou l'envoi "
            "d'une lettre recommandée.</p>")
        + art(f"{m}.2", "Subrogation",
              "<p>Après paiement de l'indemnité, nous sommes subrogés dans vos droits contre le "
              "responsable du dommage, à concurrence des sommes versées (article L.121-12).</p>"
              + sinistre_extra)
        + art(f"{m}.3", "Réclamations et médiation",
              f"<p>Pour toute réclamation, contactez votre conseiller ou le service réclamations "
              f"{BRAND.name} ({BRAND.phone_general}). Nous accusons réception sous 10 jours "
              "ouvrables et répondons sous 2 mois. En cas de désaccord persistant, vous pouvez "
              "saisir gratuitement le médiateur de l'assurance.</p>")
        + art(f"{m}.4", "Données personnelles",
              "<p>Vos données sont traitées pour la gestion du contrat, la prévention de la "
              "fraude et le respect de nos obligations légales, conformément au RGPD. Vous "
              "disposez d'un droit d'accès, de rectification, d'effacement et d'opposition "
              f"auprès du délégué à la protection des données de {COMPANY}.</p>")
        + art(f"{m}.5", "Autorité de contrôle",
              "<p>L'autorité chargée du contrôle de l'assureur est l'Autorité de contrôle "
              "prudentiel et de résolution (ACPR).</p>"),
    )


# ── Habitation ────────────────────────────────────────────────────────────────

def habitation() -> tuple[str, str, str]:
    html = section(
        "1. VOTRE CONTRAT",
        art("1.1", "Composition du contrat",
            "<p>Votre contrat Multirisque Habitation se compose des présentes conditions "
            "générales, qui décrivent les garanties et leurs limites, et des conditions "
            "particulières, qui précisent votre situation, la formule choisie (Essentiel, Confort "
            "ou Confort Plus), les capitaux assurés et le montant des franchises. Les conditions "
            "particulières prévalent sur les conditions générales.</p>")
        + art("1.2", "Objet du contrat",
              "<p>Le contrat garantit les dommages subis par vos biens immobiliers et mobiliers "
              "situés à l'adresse du risque, votre responsabilité civile d'occupant et de "
              "particulier, ainsi que l'assistance et la protection juridique selon la formule "
              "souscrite.</p>")
        + art("1.3", "Formules proposées",
              table(["Garantie", "Essentiel", "Confort", "Confort Plus"], [
                  ["Incendie, explosion, foudre", "Oui", "Oui", "Oui"],
                  ["Dégâts des eaux et gel", "Oui", "Oui", "Oui"],
                  ["Tempête, grêle, neige", "Oui", "Oui", "Oui"],
                  ["Catastrophes naturelles et technologiques", "Oui", "Oui", "Oui"],
                  ["Vol et vandalisme", "—", "Oui", "Oui"],
                  ["Bris de glace", "—", "Oui", "Oui"],
                  ["Dommages électriques", "—", "Option", "Oui"],
                  ["Mobilier en valeur à neuf", "—", "—", "Oui"],
                  ["Relogement et assistance", "7 nuits", "15 nuits", "30 nuits"],
              ])),
    ) + section(
        "2. DÉFINITIONS",
        defs([
            ("Assuré", "le souscripteur, son conjoint ou partenaire, les personnes vivant "
             "habituellement à son foyer et leurs enfants mineurs."),
            ("Bâtiment", "les constructions à l'adresse du risque, y compris les "
             "aménagements immobiliers, clôtures, murs de soutènement et installations fixes."),
            ("Mobilier", "les meubles, vêtements, appareils et objets usuels appartenant à "
             "l'assuré, à l'exclusion des véhicules à moteur."),
            ("Objets de valeur", "bijoux et objets en métal précieux de plus de 1 500 € "
             "pièce, ainsi que les tableaux, collections et objets d'art."),
            ("Franchise", "somme restant à la charge de l'assuré pour chaque sinistre."),
            ("Vétusté", "dépréciation d'un bien due à l'âge, l'usage ou l'entretien."),
            ("Valeur à neuf", "prix de reconstruction ou de remplacement par un bien neuf "
             "équivalent, au jour du sinistre."),
            ("Sinistre", "réalisation d'un événement susceptible de mettre en jeu les "
             "garanties ; l'ensemble des dommages issus d'une même cause constitue un seul sinistre."),
            ("Tiers", "toute personne autre que l'assuré."),
        ]),
    ) + section(
        "3. LES GARANTIES DE VOS BIENS",
        art("3.1", "Incendie et événements assimilés",
            "<p>Nous garantissons les dommages matériels causés par l'incendie, l'explosion, la "
            "foudre, la chute d'appareils aériens, le choc d'un véhicule terrestre identifié et "
            "les fumées accidentelles.</p>")
        + art("3.2", "Dégâts des eaux et gel",
              "<p>Nous garantissons les dommages causés par les fuites et ruptures accidentelles "
              "de conduites non enterrées, de chéneaux et gouttières, les débordements "
              "d'appareils à effet d'eau, les infiltrations accidentelles par les toitures et "
              "joints d'étanchéité, ainsi que le gel des canalisations intérieures. Les frais de "
              "recherche de fuite sont pris en charge jusqu'à 2 000 €.</p>"
              "<p>Les sinistres entre occupants d'un même immeuble sont réglés selon la "
              "convention IRSI : l'assureur de l'occupant du local sinistré gère le dossier et "
              "exerce les recours. Un constat amiable dégât des eaux doit être établi avec le "
              "voisin concerné. Franchise : <b>250 €</b> par sinistre.</p>"
              + excl(["les dommages dus à un défaut d'entretien ou de réparation caractérisé et "
                      "connu de l'assuré ;", "les remontées capillaires, condensations et "
                      "humidité permanentes ;", "les infiltrations par les murs et façades ;",
                      "le coût de réparation des appareils à l'origine de la fuite."]))
        + art("3.3", "Vol et vandalisme (formules Confort et Confort Plus)",
              "<p>Nous garantissons la disparition, la destruction ou la détérioration du "
              "mobilier à la suite d'un vol ou d'une tentative de vol commis par effraction, "
              "escalade, usage de fausses clés, agression ou introduction clandestine, ainsi "
              "que les actes de vandalisme commis à l'intérieur des locaux. Le dépôt de plainte "
              "dans les 48 heures est obligatoire. Les objets de valeur sont garantis dans la "
              "limite de 30 % du capital mobilier.</p>")
        + art("3.4", "Tempête, grêle et poids de la neige",
              "<p>Nous garantissons les dommages causés au bâtiment et au mobilier par l'action "
              "directe du vent ou le choc d'un objet projeté par le vent, lorsque ce phénomène "
              "détruit ou endommage un nombre important de bâtiments de bonne construction dans "
              "la commune ou les communes avoisinantes, ou atteint une vitesse supérieure à "
              "100 km/h. Sont également garantis les dommages de grêle et de poids de la neige "
              "sur les toitures, ainsi que les dommages de mouille causés par la pluie ou la "
              "neige pénétrant à l'intérieur dans les 48 heures suivant la destruction partielle "
              "du bâtiment.</p>"
              "<p>Franchise événements climatiques : <b>300 €</b> par sinistre.</p>"
              + excl(["les dommages aux clôtures, stores, antennes et vérandas non conformes "
                      "aux règles de l'art ;", "les dommages aux bâtiments en cours de "
                      "construction non clos et couverts ;", "les dommages dus à un défaut "
                      "d'entretien de la toiture."]))
        + art("3.5", "Bris de glace (formules Confort et Confort Plus)",
              "<p>Nous garantissons le bris accidentel des vitrages, vérandas, inserts de "
              "cheminée, plaques vitrocéramiques et panneaux solaires, frais de pose et de "
              "clôture provisoire compris.</p>")
        + art("3.6", "Dommages électriques",
              "<p>Nous garantissons les dommages causés par la foudre ou une surtension aux "
              "appareils électriques et électroniques et aux installations électriques. "
              "L'indemnité tient compte d'une vétusté de 10 % par an au-delà de deux ans, "
              "plafonnée à 70 %.</p>"),
    ) + section(
        "4. LES ÉVÉNEMENTS NATURELS ET TECHNOLOGIQUES",
        art("4.1", "Catastrophes naturelles",
            "<p>Conformément aux articles L.125-1 et suivants du Code des assurances, nous "
            "garantissons les dommages matériels directs non assurables ayant pour cause "
            "déterminante l'intensité anormale d'un agent naturel (inondation, coulée de boue, "
            "sécheresse et réhydratation des sols, mouvement de terrain, submersion marine), "
            "lorsque l'état de catastrophe naturelle est constaté par un arrêté interministériel "
            "publié au Journal officiel.</p>"
            "<p>Vous devez déclarer le sinistre au plus tard 30 jours après la publication de "
            "l'arrêté. La franchise légale est de <b>380 €</b> pour les habitations (1 520 € "
            "pour les dommages liés à la sécheresse), modulée par la réglementation en vigueur "
            "dans les communes non dotées d'un plan de prévention des risques.</p>")
        + art("4.2", "Catastrophes technologiques",
              "<p>Nous garantissons, en application de l'article L.128-1, la réparation intégrale "
              "des dommages causés à votre habitation par un accident industriel ayant fait "
              "l'objet d'un arrêté de catastrophe technologique.</p>")
        + art("4.3", "Attentats et actes de terrorisme",
              "<p>Les dommages matériels directs causés par un attentat ou un acte de terrorisme "
              "sont garantis dans les limites fixées aux conditions particulières "
              "(article L.126-2).</p>"),
    ) + section(
        "5. VOTRE RESPONSABILITÉ CIVILE",
        art("5.1", "Responsabilité civile vie privée",
            "<p>Nous garantissons les conséquences pécuniaires de la responsabilité civile que "
            "l'assuré peut encourir en raison des dommages corporels, matériels et immatériels "
            "causés aux tiers au cours de sa vie privée, y compris du fait de ses enfants, de ses "
            "animaux domestiques et de ses préposés. Plafond : 10 000 000 € pour les dommages "
            "corporels, 1 500 000 € pour les dommages matériels et immatériels.</p>")
        + art("5.2", "Responsabilité civile occupant",
              "<p>En qualité de locataire ou de propriétaire occupant, nous garantissons votre "
              "responsabilité envers le propriétaire, les voisins et les tiers en cas "
              "d'incendie, d'explosion ou de dégâts des eaux ayant pris naissance dans votre "
              "logement.</p>"),
    ) + section(
        "6. L'ASSISTANCE ET LES SERVICES",
        art("6.1", "Relogement",
            "<p>Lorsque le logement est rendu inhabitable par un sinistre garanti, nous "
            "prenons en charge les frais d'hébergement provisoire pour la durée prévue par la "
            "formule (7, 15 ou 30 nuits), dans la limite de 120 € par nuit, ainsi que les frais "
            "de déménagement et de garde-meubles.</p>")
        + art("6.2", "Assistance d'urgence",
              f"<p>Un service d'assistance joignable 24h/24 au {BRAND.phone_general} organise "
              "l'intervention d'un serrurier, d'un plombier ou d'un électricien pour mettre les "
              "lieux en sécurité, et le gardiennage des locaux si nécessaire.</p>"),
    ) + section(
        "7. FRANCHISES ET PLAFONDS",
        art("7.1", "Franchises",
            table(["Événement", "Franchise par sinistre"], [
                ["Franchise standard (incendie, vol, bris de glace, dommages électriques)", "300 €"],
                ["Dégâts des eaux et gel", "250 €"],
                ["Tempête, grêle, neige (événements climatiques)", "300 €"],
                ["Catastrophes naturelles (franchise légale)", "380 €"],
                ["Catastrophes naturelles — sécheresse", "1 520 €"],
                ["Responsabilité civile", "Néant"],
            ]))
        + art("7.2", "Plafonds",
              "<p>Les capitaux mobiliers et les plafonds par garantie figurent aux conditions "
              "particulières. Les dommages au bâtiment sont indemnisés à hauteur du coût de "
              "reconstruction, sans plafond, pour les propriétaires occupants.</p>"),
    ) + section(
        "8. VOS OBLIGATIONS EN CAS DE SINISTRE",
        art("8.1", "Déclaration et délais",
            "<p>Vous devez déclarer le sinistre dès que vous en avez connaissance et au plus tard "
            "dans les 5 jours ouvrés (2 jours ouvrés en cas de vol, 30 jours après la publication "
            "de l'arrêté pour une catastrophe naturelle), par téléphone, depuis votre espace "
            f"assuré ou par courriel à {BRAND.email_sinistres_hab}. Le non-respect de ces délais "
            "entraîne la déchéance de garantie si le retard nous a causé un préjudice.</p>")
        + art("8.2", "Mesures et justificatifs",
              "<p>Vous devez prendre toutes les mesures pour limiter l'ampleur des dommages, "
              "conserver les biens endommagés jusqu'à l'expertise et nous transmettre : "
              "photographies, factures ou justificatifs d'achat, devis de réparation, constat "
              "amiable dégât des eaux le cas échéant et récépissé de dépôt de plainte en cas de "
              "vol ou de vandalisme.</p>")
        + art("8.3", "Fausse déclaration et fraude",
              "<p>Si vous faites sciemment de fausses déclarations sur la nature, les causes, les "
              "circonstances ou le montant du sinistre, ou utilisez des documents inexacts, vous "
              "perdez tout droit à indemnité pour ce sinistre. Nous pouvons en outre résilier le "
              "contrat et réclamer le remboursement des sommes déjà versées. Les dossiers "
              "présentant des incohérences peuvent être transmis à notre service de lutte contre "
              "la fraude.</p>"),
    ) + section(
        "9. EXPERTISE ET INDEMNISATION",
        art("9.1", "Expertise",
            "<p>Les dommages sont évalués de gré à gré ou par un expert que nous mandatons. En "
            "cas de désaccord, chaque partie désigne son expert ; à défaut d'accord, un troisième "
            "expert est désigné, les frais étant partagés par moitié.</p>")
        + art("9.2", "Calcul de l'indemnité",
              "<p>Le bâtiment est indemnisé en valeur à neuf, la part de vétusté excédant 25 % "
              "restant à votre charge, sous réserve de reconstruction dans un délai de deux ans. "
              "Le mobilier est indemnisé vétusté déduite, sauf en formule Confort Plus (valeur à "
              "neuf pour les biens de moins de cinq ans). La franchise est déduite de "
              "l'indemnité.</p>")
        + art("9.3", "Délai de paiement",
              "<p>L'indemnité est versée dans les 30 jours suivant l'accord sur son montant, ou "
              "dans les 3 mois suivant la remise de l'état estimatif ou la publication de "
              "l'arrêté pour une catastrophe naturelle.</p>"),
    ) + common_provisions(10)
    return "Multirisque Habitation", "CONDITIONS GÉNÉRALES HABITATION", html


# ── Auto ──────────────────────────────────────────────────────────────────────

def _auto_core(fleet: bool) -> str:
    """Guarantee articles shared by the private auto and fleet documents."""
    veh = "chaque véhicule désigné" if fleet else "le véhicule assuré"
    return section(
        "4. LA RESPONSABILITÉ CIVILE",
        art("4.1", "Responsabilité civile automobile",
            f"<p>Conformément à l'obligation d'assurance (article L.211-1), nous garantissons la "
            f"responsabilité civile encourue du fait des dommages corporels et matériels causés "
            f"aux tiers, y compris aux passagers, par {veh}, ses accessoires et produits "
            "servant à son utilisation. Dommages corporels : sans limitation ; dommages "
            "matériels et immatériels : 100 000 000 €.</p>"),
    ) + section(
        "5. LA DÉFENSE DE VOS INTÉRÊTS",
        art("5.1", "Défense pénale et recours suite à accident",
            "<p>Nous assurons votre défense devant les juridictions répressives et exerçons, à "
            "l'amiable ou en justice, le recours contre le responsable d'un accident de la "
            "circulation, dès lors que l'intérêt en jeu dépasse 300 €.</p>"),
    ) + section(
        "6. LA PROTECTION DU CONDUCTEUR",
        art("6.1", "Garantie du conducteur",
            "<p>Nous indemnisons les dommages corporels subis par le conducteur autorisé, "
            "responsable ou non de l'accident, selon les règles du droit commun, dans la limite "
            "de 500 000 € et au-delà d'un taux d'incapacité permanente de 10 %.</p>"),
    ) + section(
        "7. BRIS DE GLACE",
        art("7.1", "Bris des glaces",
            "<p>Nous garantissons le remplacement ou la réparation du pare-brise, de la lunette "
            "arrière, des vitres latérales et du toit vitré à la suite d'un bris accidentel. La "
            "réparation d'un impact est privilégiée lorsqu'elle est techniquement possible. En "
            "formule Tous Risques, la garantie s'applique <b>sans franchise</b> lorsque "
            "l'intervention est réalisée par un réparateur agréé ; dans les autres cas, une "
            "franchise de 75 € s'applique.</p>"),
    ) + section(
        "8. LES DOMMAGES AU VÉHICULE",
        art("8.1", "Dommages tous accidents (formule Tous Risques)",
            f"<p>Nous garantissons les dommages matériels subis par {veh} par suite de "
            "collision, choc contre un corps fixe ou mobile, renversement ou versement, que le "
            "conducteur soit responsable ou non et que le tiers soit identifié ou non.</p>")
        + art("8.2", "Dommages collision avec un tiers identifié",
              "<p>Nous prenons en charge les dommages matériels résultant d'une collision avec "
              "un véhicule, un piéton ou un animal appartenant à un tiers identifié, sous "
              "déduction de la franchise contractuelle prévue à l'article 13. Lorsque le tiers "
              "est entièrement responsable, la franchise est remboursée après exercice du "
              "recours (article 12.1).</p>")
        + art("8.3", "Vandalisme",
              "<p>Nous garantissons les dommages matériels causés volontairement au véhicule par "
              "un tiers, sous réserve d'un dépôt de plainte dans les 48 heures.</p>")
        + art("8.4", "Vol et incendie",
              "<p>Nous garantissons la disparition ou la détérioration du véhicule à la suite "
              "d'un vol ou d'une tentative de vol, ainsi que les dommages causés par l'incendie, "
              "l'explosion ou la foudre. Le vol n'est garanti qu'en présence d'effraction du "
              "véhicule, de forcement de la direction ou d'agression du conducteur. Le véhicule "
              "retrouvé dans les 30 jours de la déclaration est repris par l'assuré.</p>")
        + art("8.5", "Exclusion des dommages préexistants",
              "<p>Les dommages préexistants au sinistre déclaré, ou sans lien avec les "
              "circonstances décrites, sont exclus de l'indemnisation. L'expert vérifie la "
              "cohérence entre la zone d'impact, la déclaration et les dommages constatés ; les "
              "réparations hors zone d'impact restent à la charge de l'assuré.</p>")
        + excl(["l'usure, le défaut d'entretien et les pannes mécaniques ;",
                "les dommages subis lorsque le conducteur n'a pas l'âge requis ou ne possède "
                "pas un permis en état de validité ;",
                "les dommages survenus lors de compétitions ou essais sur circuit ;",
                "les dommages causés intentionnellement par l'assuré."],
               "Exclusions propres aux dommages au véhicule :"),
    ) + section(
        "9. EXPERTISE",
        art("9.1", "Expertise contradictoire",
            "<p>Nous pouvons mandater un expert pour vérifier les circonstances du sinistre, la "
            "réalité et le montant des dommages et la cohérence des réparations proposées. Vous "
            "pouvez vous faire assister à vos frais par l'expert de votre choix ; en cas de "
            "désaccord, un tiers expert est désigné et ses honoraires partagés par moitié.</p>")
        + art("9.2", "Véhicule économiquement irréparable",
              "<p>Lorsque le montant des réparations excède la valeur de remplacement à dire "
              "d'expert, le véhicule est déclaré économiquement irréparable et la procédure VEI "
              "prévue par le Code de la route s'applique.</p>"),
    ) + section(
        "10. ÉVÉNEMENTS NATURELS",
        art("10.1", "Événements climatiques",
            "<p>Les dommages causés par la tempête, la grêle, la neige et la chute d'arbres sont "
            "garantis en formules Intermédiaire et Tous Risques, sous déduction de la franchise "
            "contractuelle.</p>")
        + art("10.2", "Catastrophes naturelles et technologiques",
              "<p>Les dommages matériels directs causés par une catastrophe naturelle reconnue "
              "par arrêté sont garantis dès lors qu'une garantie dommages a été souscrite, sous "
              "déduction de la franchise légale de 380 €.</p>"),
    ) + section(
        "11. L'ASSISTANCE",
        art("11.1", "Assistance au véhicule et aux personnes",
            f"<p>En cas de panne, d'accident ou de vol, l'assistance ({BRAND.phone_general}, "
            "24h/24) organise le dépannage ou le remorquage jusqu'au garage le plus proche, le "
            "rapatriement des passagers et, selon la formule, la mise à disposition d'un "
            "véhicule de remplacement de catégorie B pendant la durée des réparations, dans la "
            "limite de 7 jours (30 jours en cas de vol).</p>"),
    ) + section(
        "12. INDEMNISATION ET RECOURS",
        art("12.1", "Recours et subrogation",
            "<p>Après indemnisation, nous exerçons un recours contre le tiers responsable ou son "
            "assureur pour le montant des indemnités versées, dans le cadre des conventions "
            "inter-assureurs (IRSA) lorsqu'elles s'appliquent. La franchise vous est remboursée "
            "à proportion de la responsabilité du tiers.</p>")
        + art("12.2", "Délai de paiement",
              "<p>L'indemnité est versée dans les 15 jours suivant l'accord amiable ou la "
              "décision judiciaire exécutoire. En cas de vol, elle est versée au plus tôt 30 "
              "jours après la déclaration.</p>"),
    )


def _auto_franchises(fleet: bool) -> str:
    rows = [
        ["Dommages tous accidents et collision", "300 €"],
        ["Majoration conducteur novice (permis de moins de 3 ans)", "+ 300 €"],
        ["Majoration après sinistre responsable au cours des 12 derniers mois", "franchise portée à 600 €"],
        ["Vol, incendie, vandalisme", "300 €"],
        ["Bris de glace, réparateur agréé (Tous Risques)", "Néant"],
        ["Bris de glace, autre réparateur", "75 €"],
        ["Catastrophes naturelles (franchise légale)", "380 €"],
    ]
    if fleet:
        rows.append(["Marchandises transportées", "10 % du dommage, minimum 500 €"])
    return section(
        "13. FRANCHISES",
        art("13.1", "Montants",
            table(["Garantie", "Franchise par sinistre"], rows)
            + "<p>Le montant figurant aux conditions particulières prévaut sur ce barème.</p>"),
    ) + section(
        "14. EXCLUSIONS GÉNÉRALES",
        excl(["les dommages intentionnellement causés ou provoqués par l'assuré ;",
              "les dommages survenus lorsque le conducteur est sous l'empire d'un état "
              "alcoolique ou de stupéfiants, sauf preuve que le sinistre est sans relation avec "
              "cet état ;",
              "les dommages causés par la guerre civile ou étrangère ;",
              "les dommages dus aux effets de la radioactivité ;",
              "les amendes et frais s'y rapportant."],
             "Outre les exclusions propres à chaque garantie, sont exclus :"),
    )


def _auto_life(fleet: bool) -> str:
    bonus = "" if fleet else art(
        "16.2", "Clause de réduction-majoration (bonus-malus)",
        "<p>La cotisation de référence est multipliée par un coefficient de "
        "réduction-majoration fixé selon l'article A.121-1 du Code des assurances : réduction "
        "de 5 % par année sans sinistre responsable, plancher de 0,50 ; majoration de 25 % par "
        "sinistre entièrement responsable et de 12,5 % par sinistre partiellement responsable, "
        "plafond de 3,50.</p>")
    return section(
        "15. VOS DÉCLARATIONS",
        art("15.1", "À la souscription",
            "<p>Vous devez répondre exactement aux questions posées sur le conducteur, le "
            "véhicule, son usage et ses antécédents d'assurance (relevé d'information des cinq "
            "dernières années).</p>")
        + art("15.2", "En cours de contrat",
              "<p>Vous devez déclarer tout changement de véhicule, d'usage, de lieu de garage, "
              "de conducteur habituel ou toute suspension ou annulation de permis.</p>")
        + art("15.3", "Fraude et fausse déclaration",
              "<p>En cas de fausse déclaration intentionnelle ou de fraude avérée lors de la "
              "déclaration d'un sinistre (circonstances, dommages, documents ou photographies "
              "falsifiés), nous pouvons refuser l'indemnisation, résilier le contrat et "
              "réclamer le remboursement des sommes versées, sans préjudice de poursuites. Les "
              "dossiers présentant des indices de fraude sont transmis à notre cellule "
              "d'investigation.</p>"),
    ) + section(
        "16. COTISATION",
        art("16.1", "Paiement",
            "<p>La cotisation est payable aux échéances prévues aux conditions particulières. "
            "Les règles de l'article 18.4 s'appliquent en cas de non-paiement.</p>")
        + bonus,
    ) + section(
        "17. EN CAS DE SINISTRE",
        art("17.1", "Déclaration",
            "<p>Déclarez le sinistre dans les 5 jours ouvrés (2 jours en cas de vol, avec dépôt "
            f"de plainte) à {BRAND.email_sinistres_auto} ou depuis votre espace assuré, en "
            "joignant le constat amiable signé, les photographies des dommages, le procès-verbal "
            "le cas échéant et les coordonnées des témoins.</p>"),
    )


def auto() -> tuple[str, str, str]:
    html = section(
        "1. VOTRE CONTRAT",
        art("1.1", "Composition et objet",
            "<p>Votre contrat Auto se compose des présentes conditions générales et des "
            "conditions particulières. Il garantit, selon la formule souscrite, votre "
            "responsabilité civile, la protection du conducteur et les dommages subis par le "
            "véhicule désigné.</p>")
        + art("1.2", "Formules",
              table(["Garantie", "Tiers", "Intermédiaire", "Tous Risques"], [
                  ["Responsabilité civile", "Oui", "Oui", "Oui"],
                  ["Défense pénale et recours", "Oui", "Oui", "Oui"],
                  ["Protection du conducteur", "Option", "Oui", "Oui"],
                  ["Bris de glace", "Option", "Oui", "Oui, sans franchise (réparateur agréé)"],
                  ["Vol et incendie", "—", "Oui", "Oui"],
                  ["Événements climatiques", "—", "Oui", "Oui"],
                  ["Dommages tous accidents / collision", "—", "—", "Oui"],
                  ["Assistance 0 km et véhicule de remplacement", "Option", "Option", "Oui"],
              ])),
    ) + section(
        "2. DÉFINITIONS",
        defs([
            ("Accident", "tout événement soudain, imprévu et extérieur à la victime ou au "
             "véhicule, constituant la cause des dommages."),
            ("Conducteur autorisé", "toute personne conduisant le véhicule avec "
             "l'autorisation du souscripteur et titulaire d'un permis valide."),
            ("Conducteur novice", "conducteur titulaire du permis depuis moins de trois ans."),
            ("Valeur de remplacement", "valeur d'un véhicule de même modèle et de même état, "
             "déterminée à dire d'expert au jour du sinistre."),
            ("Franchise", "part du préjudice restant à la charge de l'assuré."),
            ("Tiers identifié", "personne dont le nom et l'adresse sont connus et qui est "
             "impliquée dans l'accident."),
        ]),
    ) + section(
        "3. OÙ S'EXERCENT VOS GARANTIES",
        art("3.1", "Étendue territoriale",
            "<p>Les garanties s'exercent en France métropolitaine, dans les DROM et dans les "
            "pays mentionnés sur le certificat international d'assurance (carte verte) non "
            "rayés.</p>"),
    ) + _auto_core(fleet=False) + _auto_franchises(fleet=False) + _auto_life(fleet=False) \
        + common_provisions(18)
    return "Assurance Automobile", "CONDITIONS GÉNÉRALES AUTO", html


def flotte() -> tuple[str, str, str]:
    html = section(
        "1. VOTRE CONTRAT FLOTTE",
        art("1.1", "Objet",
            "<p>Le contrat Flotte Auto assure, sous un contrat unique, l'ensemble des véhicules "
            "terrestres à moteur appartenant à l'entreprise souscriptrice ou utilisés pour ses "
            "besoins, dès lors que la flotte comprend au moins cinq véhicules.</p>")
        + art("1.2", "Adhésion des véhicules",
              "<p>Les véhicules sont assurés dès leur déclaration à l'assureur. Tout véhicule "
              "nouvellement acquis est garanti automatiquement pendant 30 jours, sous réserve "
              "de sa déclaration dans ce délai. Les sorties de flotte prennent effet à la date "
              "de déclaration.</p>")
        + art("1.3", "Conducteurs",
              "<p>Les véhicules peuvent être conduits par tout préposé de l'entreprise titulaire "
              "d'un permis valide. L'entreprise s'engage à vérifier annuellement la validité des "
              "permis de ses conducteurs.</p>"),
    ) + section(
        "2. DÉFINITIONS",
        defs([
            ("Flotte", "ensemble des véhicules déclarés au contrat."),
            ("Souscripteur", "l'entreprise signataire du contrat."),
            ("Préposé", "salarié ou mandataire autorisé à conduire un véhicule de la flotte."),
            ("Marchandises transportées", "biens transportés à titre professionnel dans un "
             "véhicule de la flotte."),
            ("Sinistralité", "rapport entre les sinistres payés ou provisionnés et les "
             "cotisations acquises sur une période d'observation."),
        ]),
    ) + section(
        "3. OÙ S'EXERCENT VOS GARANTIES",
        art("3.1", "Étendue territoriale",
            "<p>France métropolitaine, DROM et pays mentionnés sur la carte verte de chaque "
            "véhicule.</p>"),
    ) + _auto_core(fleet=True) + section(
        "MARCHANDISES TRANSPORTÉES",
        art("12.3", "Marchandises transportées",
            "<p>Lorsque l'option est souscrite, nous garantissons les dommages subis par les "
            "marchandises transportées à la suite d'un accident de la circulation, d'un "
            "incendie ou d'un vol du véhicule, dans la limite de 15 000 € par véhicule.</p>"),
    ) + _auto_franchises(fleet=True) + _auto_life(fleet=True) + section(
        "TARIFICATION DE LA FLOTTE",
        art("16.2", "Ajustement annuel",
            "<p>La cotisation est ajustée chaque année en fonction de la composition de la "
            "flotte et de sa sinistralité sur les trois derniers exercices. Une régularisation "
            "est établie à l'échéance d'après la déclaration des entrées et sorties de "
            "véhicules.</p>")
        + art("16.3", "Prévention",
              "<p>Au-delà d'une sinistralité de 70 %, nous proposons un plan de prévention "
              "(formation à l'éco-conduite, télématique, analyse des sinistres) dont la mise en "
              "œuvre peut conditionner le renouvellement.</p>"),
    ) + common_provisions(18)
    return "Assurance Flotte Automobile", "CONDITIONS GÉNÉRALES FLOTTE AUTO", html


# ── Complémentaire santé ──────────────────────────────────────────────────────

def sante() -> tuple[str, str, str]:
    html = section(
        "1. VOTRE CONTRAT",
        art("1.1", "Composition",
            "<p>Votre contrat de complémentaire santé se compose des présentes conditions "
            "générales, du tableau des garanties de la formule choisie et du certificat "
            "d'adhésion qui précise les bénéficiaires et la date d'effet.</p>")
        + art("1.2", "Objet",
              "<p>Le contrat rembourse, en complément du régime obligatoire d'assurance maladie, "
              "tout ou partie des frais de santé engagés par les bénéficiaires. Il respecte le "
              "cahier des charges des contrats responsables et solidaires (articles L.871-1 et "
              "R.871-1 du Code de la sécurité sociale), y compris le dispositif 100 % Santé.</p>")
        + art("1.3", "Définitions",
              defs([
                  ("Base de remboursement (BR)", "tarif servant de référence au régime "
                   "obligatoire pour calculer son remboursement."),
                  ("Bénéficiaire", "l'adhérent et les membres de sa famille inscrits au "
                   "certificat d'adhésion."),
                  ("Délai de carence", "période pendant laquelle une garantie n'est pas "
                   "encore acquise."),
                  ("Dépassement d'honoraires", "part des honoraires excédant la base de "
                   "remboursement ; elle est prise en charge à hauteur de 100 % BR "
                   "supplémentaires pour les médecins non adhérents à l'OPTAM."),
                  ("Forfait journalier", "participation due pour chaque journée "
                   "d'hospitalisation, prise en charge sans limitation de durée."),
                  ("Reste à charge", "somme restant due par le bénéficiaire après les "
                   "remboursements du régime obligatoire et du contrat."),
              ])),
    ) + section(
        "2. LES GARANTIES",
        art("2.1", "Conditions de garantie",
            "<p>Les remboursements sont exprimés en pourcentage de la base de remboursement, "
            "régime obligatoire inclus, ou en euros par an et par bénéficiaire. Ils ne peuvent "
            "excéder les frais réellement engagés. Aucune garantie n'est due pour un acte non "
            "pris en charge par le régime obligatoire, sauf mention contraire.</p>")
        + art("2.2", "Tableau des garanties",
              table(["Poste", "Essentiel", "Équilibre", "Équilibre Plus", "Sérénité", "Santé Plus"], [
                  ["Consultations généraliste et spécialiste", "100 % BR", "125 % BR", "150 % BR", "200 % BR", "200 % BR"],
                  ["Hospitalisation — frais de séjour", "100 % BR", "100 % BR", "100 % BR", "100 % BR", "100 % BR"],
                  ["Chambre particulière (par jour)", "—", "30 €", "40 €", "60 €", "80 €"],
                  ["Soins dentaires", "100 % BR", "100 % BR", "100 % BR", "100 % BR", "100 % BR"],
                  ["Prothèses dentaires (hors 100 % Santé)", "125 % BR", "150 % BR", "200 % BR", "300 % BR", "200 % BR"],
                  ["Optique — équipement (monture + verres)", "100 € / 2 ans", "150 € / 2 ans", "200 € / 2 ans", "300 € / an", "350 € / 2 ans"],
                  ["Forfait naissance", "—", "150 €", "500 €", "300 €", "500 €"],
                  ["Médecines douces (par an)", "—", "60 €", "100 €", "150 €", "200 €"],
              ]))
        + art("2.3", "Précisions par poste",
              "<p><b>Optique :</b> le renouvellement de l'équipement est possible tous les deux "
              "ans pour les adultes (tous les ans en formule Sérénité et en cas d'évolution de la "
              "vue). <b>Dentaire :</b> les prothèses supérieures à 1 000 € donnent lieu à un devis "
              "préalable ; le service Infos Devis analyse le devis sous 48 heures. "
              "<b>Hospitalisation :</b> le forfait journalier et le ticket modérateur sont "
              "remboursés intégralement ; la chambre particulière est prise en charge dans la "
              "limite de 60 jours par an en psychiatrie. <b>Maternité :</b> le forfait naissance "
              "est versé sur présentation de l'acte de naissance ou d'adoption.</p>")
        + art("2.4", "Ce que nous ne garantissons pas",
              excl(["les dépassements d'honoraires et majorations exclus par la "
                    "réglementation des contrats responsables ;",
                    "la participation forfaitaire et les franchises médicales du régime "
                    "obligatoire ;",
                    "les frais engagés avant la date d'effet ou pendant un délai de carence ;",
                    "les cures thermales hors prescription et la chirurgie esthétique non "
                    "réparatrice."])),
    ) + section(
        "3. LES SERVICES ET L'ASSISTANCE",
        art("3.1", "Services",
            f"<p>Tiers payant chez les professionnels partenaires, analyse des devis, "
            f"téléconsultation 24h/24 et service d'information santé au {BRAND.phone_sante}.</p>")
        + art("3.2", "Assistance santé à domicile",
              "<p>Après une hospitalisation de plus de 48 heures ou une immobilisation de plus "
              "de 5 jours, nous organisons et prenons en charge une aide-ménagère (jusqu'à 20 "
              "heures), la garde des enfants ou des animaux et la livraison de médicaments.</p>"),
    ) + section(
        "4. DISPOSITIONS SPÉCIFIQUES AUX CONTRATS COLLECTIFS",
        art("4.1", "Adhésion",
            "<p>Lorsque le contrat est souscrit par un employeur au profit de ses salariés "
            "(contrats référencés PRV-COL), l'adhésion est obligatoire pour la catégorie de "
            "personnel définie à l'acte de mise en place, sous réserve des dispenses légales.</p>")
        + art("4.2", "Plafond annuel et franchise",
              "<p>Pour les contrats collectifs, les remboursements sont limités à un plafond "
              "annuel de <b>50 000 €</b> par bénéficiaire, après application d'une franchise "
              "annuelle de <b>150 €</b> par bénéficiaire, sauf pour les postes 100 % Santé.</p>")
        + art("4.3", "Portabilité",
              "<p>En cas de rupture du contrat de travail ouvrant droit à l'assurance chômage, "
              "les garanties sont maintenues gratuitement pendant la durée d'indemnisation, dans "
              "la limite de 12 mois.</p>"),
    ) + section(
        "5. LES REMBOURSEMENTS",
        art("5.1", "Modalités",
            "<p>Grâce à la télétransmission avec le régime obligatoire, la plupart des "
            "remboursements sont automatiques et versés sous 48 heures. À défaut, adressez-nous "
            f"les décomptes et factures à {BRAND.email_sante} ou depuis votre espace assuré.</p>")
        + art("5.2", "Contrôle",
              "<p>Nous pouvons demander toute pièce justificative et, avec votre accord, faire "
              "procéder à un contrôle médical par un praticien de notre choix. Toute fraude ou "
              "fausse déclaration entraîne la perte du droit aux prestations concernées.</p>"),
    ) + common_provisions(6)
    return "Complémentaire Santé", "CONDITIONS GÉNÉRALES COMPLÉMENTAIRE SANTÉ", html


# ── Rendering ─────────────────────────────────────────────────────────────────

def _hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


TEAL = _hex_rgb("#2EC4B6")


def draw_logo(page: fitz.Page, x: float, y: float, height: float) -> None:
    """Vector copy of frontend/public/prevaiq-logo.svg (its text needs the Inter font)."""
    s = height / 72

    def pt(px: float, py: float) -> fitz.Point:
        return fitz.Point(x + px * s, y + py * s)

    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(pt(2, 2), pt(70, 70)), radius=18 / 68)
    shape.finish(fill=BRAND.color_rgb, color=None)
    shape.draw_polyline([pt(21, 38.5), pt(34.5, 19), pt(51, 38.5), pt(43.5, 38.5),
                         pt(34.5, 27.75), pt(27, 38.5)])
    shape.finish(fill=TEAL, color=None, closePath=True)
    shape.draw_rect(fitz.Rect(pt(21.5, 43), pt(51.5, 50)))
    shape.finish(fill=(1, 1, 1), color=None)
    shape.draw_circle(pt(236, 18), 6 * s)
    shape.finish(fill=TEAL, color=None)
    shape.commit()
    size = 34 * s
    page.insert_text(pt(86, 47), "Preva", fontname="hebo", fontsize=size, color=BRAND.color_rgb)
    preva_w = fitz.get_text_length("Preva", fontname="hebo", fontsize=size)
    page.insert_text(fitz.Point(x + 86 * s + preva_w, y + 47 * s), "IQ", fontname="hebo",
                     fontsize=size, color=TEAL)


def _cover(product: str, title: str) -> str:
    return (
        f'<div style="text-align:center"><p style="font-size:30pt;color:{BRAND.color_hex};'
        f'margin-top:150pt"><b>{BRAND.name_upper}</b></p>'
        f'<p style="font-size:13pt;color:#2EC4B6">{product}</p>'
        f'<p style="font-size:18pt;color:{BRAND.color_hex};margin-top:30pt"><b>{title}</b></p>'
        f'<p style="font-size:10pt">{EDITION}</p>'
        f'<div class="box" style="margin-top:120pt"><p style="text-align:center">{LEGAL}</p></div>'
        "</div>"
    )


def render(filename: str, product: str, title: str, body: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 72, -50, -56)
    headings: list[tuple[int, str, int]] = []

    def record(pos) -> None:
        if pos.heading and pos.open_close & 1 and pos.text:
            headings.append((pos.heading - 1, pos.text.strip(), pos.page))

    writer = fitz.DocumentWriter(str(path))
    page_no = 0
    for html in (_cover(product, title), f"<h1>{title}</h1>{body}"):
        story = fitz.Story(html=html, user_css=CSS)
        more = 1
        while more:
            page_no += 1
            device = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.element_positions(record, {"page": page_no})
            story.draw(device)
            writer.end_page()
    writer.close()

    doc = fitz.open(path)
    for page in doc:
        if page.number == 0:
            draw_logo(page, 207, 60, 50)
            continue
        draw_logo(page, 50, 22, 30)
        page.insert_text((300, 42), f"{title} — {EDITION}", fontsize=7.5, color=BRAND.color_rgb)
        page.draw_line((50, 62), (545, 62), color=(0.18, 0.77, 0.71), width=0.8)
        page.insert_text((50, 815), LEGAL, fontsize=6.5, color=(0.4, 0.4, 0.4))
        page.insert_text((520, 815), f"{page.number + 1}/{doc.page_count}", fontsize=7.5)
    doc.set_toc([[min(max(lvl, 1), 2), text, pg] for lvl, text, pg in headings if lvl <= 2])
    doc.set_metadata({
        "title": f"{title} — {COMPANY}",
        "author": COMPANY,
        "subject": f"{product} — document fictif de démonstration",
        "keywords": f"{BRAND.name}, conditions générales, {product}",
        "creator": "scripts/generate_policy_pdfs.py",
    })
    doc.saveIncr()
    doc.close()
    return path


DOCUMENTS = {
    "conditions-generales-habitation": habitation,
    "conditions-generales-auto": auto,
    "conditions-generales-flotte-auto": flotte,
    "complementaire-sante": sante,
}


def main() -> None:
    prefix = BRAND.name.lower()
    for suffix, build in DOCUMENTS.items():
        product, title, body = build()
        path = render(f"{prefix}-{suffix}.pdf", product, title, body)
        with fitz.open(path) as doc:
            print(f"{path.relative_to(ROOT)}: {doc.page_count} pages, "
                  f"{sum(len(p.get_text()) for p in doc)} chars")


if __name__ == "__main__":
    main()

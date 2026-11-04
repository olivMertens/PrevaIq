from __future__ import annotations

from typing import Final

SUPPORTED_LANGUAGES: Final = ("en", "fr", "de")
DEFAULT_LANGUAGE: Final = "en"

_LANGUAGE_NAMES: Final = {
    "en": "English",
    "fr": "French",
    "de": "German",
}

_LANGUAGE_INSTRUCTIONS: Final = {
    "en": (
        "Write every human-readable generated value in English. Preserve source quotations, "
        "citations, identifiers, codes, URLs, dates, numbers, enum values, and French legal terms."
    ),
    "fr": (
        "Rédige toutes les valeurs générées lisibles en français. Conserve sans modification "
        "les citations source, identifiants, codes, URL, dates, nombres, valeurs d'énumération "
        "et termes juridiques français."
    ),
    "de": (
        "Schreibe alle menschenlesbaren generierten Werte auf Deutsch. Bewahre Quellenzitate, "
        "Belege, Identifikatoren, Codes, URLs, Datumsangaben, Zahlen, Enum-Werte und "
        "französische Rechtsbegriffe unverändert auf."
    ),
}


class UnsupportedLanguageError(ValueError):
    """Raised when an API caller requests an unsupported output language."""


def normalize_language(
    language: str | None,
    *,
    default: str = DEFAULT_LANGUAGE,
    strict: bool = False,
) -> str:
    normalized = (language or "").strip().lower().split("-", 1)[0]
    if not normalized:
        return default
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    if strict:
        raise UnsupportedLanguageError(
            f"Unsupported language '{language}'. Supported languages: "
            f"{', '.join(SUPPORTED_LANGUAGES)}."
        )
    return default


def require_language(language: str | None, *, default: str = DEFAULT_LANGUAGE) -> str:
    """Normalize an externally supplied locale and reject unsupported values."""
    return normalize_language(language, default=default, strict=True)


def language_name(language: str | None) -> str:
    return _LANGUAGE_NAMES[normalize_language(language)]


def language_instruction(language: str | None) -> str:
    return _LANGUAGE_INSTRUCTIONS[normalize_language(language)]


_MESSAGES: Final = {
    "application_not_found": {
        "en": "Application not found.",
        "fr": "Dossier introuvable.",
        "de": "Antrag nicht gefunden.",
    },
    "analysis_started": {
        "en": "Analysis started.",
        "fr": "Analyse lancée.",
        "de": "Analyse gestartet.",
    },
    "processing_started": {
        "en": "Processing started in the background. Poll the application endpoint for status.",
        "fr": "Traitement lancé en arrière-plan. Interrogez le dossier pour connaître son statut.",
        "de": "Die Verarbeitung wurde im Hintergrund gestartet. Fragen Sie den Antrag für den Status ab.",
    },
    "analysis_in_progress": {
        "en": "An analysis is already in progress for this application.",
        "fr": "Une analyse est déjà en cours pour ce dossier.",
        "de": "Für diesen Antrag läuft bereits eine Analyse.",
    },
    "translation_failed": {
        "en": "The requested analysis translation could not be completed.",
        "fr": "La traduction demandée de l'analyse n'a pas pu être effectuée.",
        "de": "Die angeforderte Übersetzung der Analyse konnte nicht abgeschlossen werden.",
    },
    "webiq_not_configured": {
        "en": "Web intelligence is unavailable because Web IQ is not configured.",
        "fr": "La recherche web est indisponible car Web IQ n'est pas configuré.",
        "de": "Web-Intelligenz ist nicht verfügbar, da Web IQ nicht konfiguriert ist.",
    },
    "webiq_temporarily_unavailable": {
        "en": "Web intelligence is temporarily unavailable.",
        "fr": "La recherche web est momentanément indisponible.",
        "de": "Web-Intelligenz ist vorübergehend nicht verfügbar.",
    },
    "webiq_no_results": {
        "en": "No web results were found.",
        "fr": "Aucun résultat web n'a été trouvé.",
        "de": "Es wurden keine Webergebnisse gefunden.",
    },
    "webiq_missing_location": {
        "en": "Web verification was not performed: the claim has no municipality to search.",
        "fr": "Vérification web non effectuée : aucune commune du sinistre à rechercher.",
        "de": "Keine Webprüfung durchgeführt: Für den Schaden ist keine Gemeinde angegeben.",
    },
    "fraud_siu_suspect_images": {
        "en": "{count} suspicious image(s) — SIU review recommended.",
        "fr": "{count} image(s) suspecte(s) — contrôle SIU recommandé.",
        "de": "{count} verdächtige(s) Bild(er) — SIU-Prüfung empfohlen.",
    },
    "fraud_siu_suspect_images_declaration": {
        "en": "{count} suspicious image(s) and an inconsistent declaration — SIU review recommended.",
        "fr": "{count} image(s) suspecte(s) et déclaration incohérente — contrôle SIU recommandé.",
        "de": (
            "{count} verdächtige(s) Bild(er) und widersprüchliche Schadenmeldung — "
            "SIU-Prüfung empfohlen."
        ),
    },
    "fraud_siu_high_risk": {
        "en": "High risk detected — SIU review recommended.",
        "fr": "Risque élevé détecté — contrôle SIU recommandé.",
        "de": "Hohes Risiko erkannt — SIU-Prüfung empfohlen.",
    },
    "fraud_siu_high_risk_declaration": {
        "en": "High risk detected and an inconsistent declaration — SIU review recommended.",
        "fr": "Risque élevé détecté et déclaration incohérente — contrôle SIU recommandé.",
        "de": "Hohes Risiko erkannt und widersprüchliche Schadenmeldung — SIU-Prüfung empfohlen.",
    },
    "fraud_suspect_image_label": {
        "en": "Suspicious image: {filename}",
        "fr": "Image suspecte : {filename}",
        "de": "Verdächtiges Bild: {filename}",
    },
    "fraud_suspect_image_detail": {
        "en": "Authenticity score {score}% — manual review recommended.",
        "fr": "Score d'authenticité {score} % — vérification manuelle recommandée.",
        "de": "Echtheitswert {score} % — manuelle Prüfung empfohlen.",
    },
    "fraud_inconsistent_declaration_label": {
        "en": "Inconsistent declaration",
        "fr": "Déclaration incohérente",
        "de": "Widersprüchliche Schadenmeldung",
    },
    "fraud_inconsistent_declaration_detail": {
        "en": "Declaration/evidence consistency {score}% — discrepancies to investigate.",
        "fr": "Concordance déclaration/preuves {score} % — écarts à instruire.",
        "de": "Übereinstimmung Meldung/Belege {score} % — Abweichungen zu prüfen.",
    },
    "fraud_image_content_filter": {
        "en": "Image rejected by the Azure content filter",
        "fr": "Image rejetée par le filtre de contenu Azure",
        "de": "Bild vom Azure-Inhaltsfilter abgelehnt",
    },
    "fraud_image_deployment_missing": {
        "en": "Vision deployment not found — check FRAUD_VISION_DEPLOYMENT",
        "fr": "Déploiement vision introuvable — vérifier FRAUD_VISION_DEPLOYMENT",
        "de": "Vision-Deployment nicht gefunden — FRAUD_VISION_DEPLOYMENT prüfen",
    },
    "fraud_image_rate_limited": {
        "en": "Rate limit reached — retry in a few moments",
        "fr": "Limite de débit atteinte — réessayer dans quelques instants",
        "de": "Ratenlimit erreicht — bitte gleich erneut versuchen",
    },
    "fraud_image_timeout": {
        "en": "The analysis timed out",
        "fr": "Délai d'attente dépassé pour l'analyse",
        "de": "Zeitüberschreitung bei der Analyse",
    },
    "fraud_image_auth_error": {
        "en": "Azure OpenAI authentication error",
        "fr": "Erreur d'authentification Azure OpenAI",
        "de": "Azure OpenAI-Authentifizierungsfehler",
    },
    "fraud_image_analysis_error": {
        "en": "Image analysis error",
        "fr": "Erreur d'analyse de l'image",
        "de": "Fehler bei der Bildanalyse",
    },
    "fraud_image_unstructured": {
        "en": "Analysis error — unstructured result",
        "fr": "Erreur d'analyse — résultat non structuré",
        "de": "Analysefehler — unstrukturiertes Ergebnis",
    },
    "fraud_image_unavailable": {
        "en": "The file could not be loaded",
        "fr": "Impossible de charger le fichier",
        "de": "Die Datei konnte nicht geladen werden",
    },
}


def localized_message(key: str, language: str | None) -> str:
    """Return generated API status/error text in the requested language."""
    locale = normalize_language(language)
    messages = _MESSAGES.get(key)
    if messages is None:
        raise KeyError(key)
    return messages[locale]

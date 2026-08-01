"""Integración con TMDb (búsqueda, portadas, sinopsis) y OMDb (nota IMDb).

Se documenta aquí la elección de fuente para la nota del Modo 1 de la ruleta:
IMDb no ofrece una API pública oficial, así que usamos OMDb
(https://www.omdbapi.com/), que expone su campo `imdbRating` gratis para
uso personal/no comercial.
"""

from dataclasses import dataclass

import requests
from django.conf import settings

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
OMDB_BASE_URL = "https://www.omdbapi.com/"
REQUEST_TIMEOUT = 8


class MovieAPIError(Exception):
    """Fallo de red o de la API externa (TMDb/OMDb) al consultar películas."""


@dataclass
class TMDbResult:
    tmdb_id: int
    title: str
    year: str
    poster_path: str
    overview: str
    media_type: str = "movie"

    @property
    def poster_url(self):
        return poster_url(self.poster_path)


def tmdb_search(query, media_type="movie"):
    """Busca películas o series por título en TMDb. Devuelve una lista de
    TMDbResult. `media_type` es "movie" o "tv" — cada uno pega a un endpoint
    de búsqueda distinto de TMDb, ya que son catálogos separados."""
    endpoint = "tv" if media_type == "tv" else "movie"
    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/search/{endpoint}",
            params={"api_key": settings.TMDB_API_KEY, "query": query, "language": "es-ES"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MovieAPIError("No se pudo contactar con TMDb.") from exc

    data = response.json()
    results = []
    for item in data.get("results", []):
        if media_type == "tv":
            title = item.get("name") or item.get("original_name") or "(sin título)"
            date = item.get("first_air_date") or ""
        else:
            title = item.get("title") or item.get("original_title") or "(sin título)"
            date = item.get("release_date") or ""
        results.append(TMDbResult(
            tmdb_id=item["id"],
            title=title,
            year=date[:4],
            poster_path=item.get("poster_path") or "",
            overview=item.get("overview") or "",
            media_type=media_type,
        ))
    return results


def tmdb_get_details(tmdb_id, media_type="movie"):
    """Detalles de una película o serie por su id de TMDb, incluido el
    imdb_id (bajo `external_ids`)."""
    endpoint = "tv" if media_type == "tv" else "movie"
    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}",
            params={
                "api_key": settings.TMDB_API_KEY,
                "language": "es-ES",
                "append_to_response": "external_ids",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MovieAPIError("No se pudo contactar con TMDb.") from exc

    return response.json()


def omdb_get_imdb_rating(imdb_id):
    """Nota IMDb (0-10) de una película a partir de su imdb_id, vía OMDb.
    Devuelve None si OMDb no tiene nota (p.ej. "N/A") o no encuentra el título."""
    if not imdb_id:
        return None
    try:
        response = requests.get(
            OMDB_BASE_URL,
            params={"apikey": settings.OMDB_API_KEY, "i": imdb_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MovieAPIError("No se pudo contactar con OMDb.") from exc

    data = response.json()
    rating = data.get("imdbRating")
    if not rating or rating == "N/A":
        return None
    try:
        return float(rating)
    except ValueError:
        return None


def poster_url(poster_path):
    return f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else ""

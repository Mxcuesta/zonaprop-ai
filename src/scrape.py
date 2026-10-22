"""Download a ZonaProp search into one CSV.

The search page embeds the first result set. Later HTML pages are blocked, so
paging uses the same POST the site sends when the page number changes.
"""

import argparse
import copy
import csv
import html
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "https://www.zonaprop.com.ar/rplis-api/postings"
ORIGIN = "https://www.zonaprop.com.ar"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
RETRIES = 3
# Last page observed to repeat an earlier page sits just above this.
CAP_SEARCH_LIMIT = 1500

LOCATION_FIELDS = {
    "province": "province",
    "city": "city",
    "zone": "zone",
    "subzone": "subZone",
    "valuezone": "valueZone",
}
PUBLISHER_TYPES = {
    "1": "particular",
    "2": "inmobiliaria",
    "3": "desarrollador",
    "4": "corredor",
}
TIPO = {
    "departamento": "departamento",
    "departamentos": "departamento",
    "casa": "casa",
    "casas": "casa",
    "ph": "ph",
    "terreno": "terreno",
    "terrenos": "terreno",
}

COLUMNS = [
    "id",
    "url",
    "titulo",
    "precio_usd",
    "precio_monto",
    "precio_moneda",
    "precio_texto",
    "precio_min_usd",
    "precio_max_usd",
    "precio_m2_usd",
    "barrio",
    "zona",
    "ciudad",
    "direccion",
    "direccion_visibilidad",
    "latitud",
    "longitud",
    "ambientes",
    "dormitorios",
    "banos",
    "toilettes",
    "cocheras",
    "antiguedad",
    "disposicion",
    "orientacion",
    "luminoso",
    "descripcion",
    "tipo",
    "tipo_publicado",
    "tipo_aviso",
    "superficie_total",
    "superficie_cubierta",
    "superficie_descubierta",
    "superficie_descubierta_origen",
    "superficie_total_texto",
    "superficie_cubierta_texto",
    "superficie_descubierta_texto",
    "expensas",
    "expensas_moneda",
    "anunciante",
    "anunciante_id",
    "tipo_anunciante",
    "fecha_modificacion",
    "reservado",
    "estado",
    "apto_credito",
    "tiene_video",
    "tiene_tour",
    "tiene_planos",
    "fotos",
]

_thread = threading.local()
_print_lock = threading.Lock()


def log(message):
    with _print_lock:
        print(message, flush=True)


def opener():
    if not hasattr(_thread, "opener"):
        _thread.opener = urllib.request.build_opener()
    return _thread.opener


def norm(text):
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower().strip()


def parse_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def number_cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def is_square_meters(measure):
    text = norm(measure).replace("²", "2").replace(" ", "")
    return text in {"m2"}


def clean_html(value):
    if not value:
        return ""
    text = html.unescape(html.unescape(str(value)))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def request(url, *, data=None, accept="application/json", referer=None, timeout=40):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "es-AR,es;q=0.9",
        "Origin": ORIGIN,
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers["Content-Type"] = "application/json"
        headers["X-Requested-With"] = "XMLHttpRequest"
    last_error = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with opener().open(req, timeout=timeout) as response:
                body = response.read()
            return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1.2 * (attempt + 1))
    raise last_error


def request_json(url, payload, referer):
    raw = request(url, data=json.dumps(payload).encode("utf-8"), referer=referer)
    return json.loads(raw.decode("utf-8"))


def load_state(page_html):
    marker = "window.__PRELOADED_STATE__ = "
    start = page_html.find(marker)
    if start < 0:
        return None
    start = page_html.find("{", start)
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(page_html[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(page_html[start : index + 1])
    return None


def empty_body():
    return {
        "q": None,
        "direccion": None,
        "moneda": "",
        "preciomin": None,
        "preciomax": None,
        "services": "",
        "general": "",
        "searchbykeyword": "",
        "amenidades": "",
        "caracteristicasprop": None,
        "comodidades": "",
        "disposicion": None,
        "roomType": "",
        "outside": "",
        "areaPrivativa": "",
        "areaComun": "",
        "multipleRets": "",
        "tipoDePropiedad": None,
        "subtipoDePropiedad": None,
        "tipoDeOperacion": None,
        "garages": None,
        "antiguedad": None,
        "expensasminimo": None,
        "expensasmaximo": None,
        "withoutguarantor": None,
        "habitacionesminimo": 0,
        "habitacionesmaximo": 0,
        "ambientesminimo": 0,
        "ambientesmaximo": 0,
        "banos": None,
        "superficieCubierta": 1,
        "idunidaddemedida": 1,
        "metroscuadradomin": None,
        "metroscuadradomax": None,
        "tipoAnunciante": "ALL",
        "grupoTipoDeMultimedia": "",
        "publicacion": None,
        "sort": "relevance",
        "etapaDeDesarrollo": "",
        "auctions": None,
        "polygonApplied": None,
        "idInmobiliaria": None,
        "excludePostingContacted": "",
        "banks": "",
        "places": "",
        "condominio": "",
        "preTipoDeOperacion": "",
        "city": None,
        "province": None,
        "zone": None,
        "valueZone": None,
        "subZone": None,
        "coordenates": None,
    }


def applied_options(applied, type_name):
    for item in applied:
        if item.get("type") == type_name:
            return item.get("options") or []
    return []


def bodies_from_state(state):
    listing = state["listStore"]
    applied = listing.get("appliedFilters") or []
    base = empty_body()
    operations = [option.get("min") for option in applied_options(applied, "operationType") if option.get("min")]
    types = [option.get("min") for option in applied_options(applied, "realestateType") if option.get("min")]
    publishers = [option.get("min") for option in applied_options(applied, "publisherType") if option.get("min")]
    sorts = [option.get("min") for option in applied_options(applied, "sort") if option.get("min")]
    if operations:
        base["tipoDeOperacion"] = str(operations[0])
    if types:
        base["tipoDePropiedad"] = ",".join(str(item) for item in types)
    if publishers:
        base["tipoAnunciante"] = str(publishers[0])
    if sorts:
        base["sort"] = str(sorts[0])

    locations = []
    for option in applied_options(applied, "location"):
        kind = LOCATION_FIELDS.get(option.get("type") or "")
        value = str(option.get("min") or "").strip()
        if kind and value:
            locations.append((kind, value, option.get("label") or value))
    if not locations:
        locations.append((None, None, "busqueda"))

    queries = []
    for kind, value, label in locations:
        body = copy.deepcopy(base)
        if kind:
            body[kind] = value
        queries.append(
            {
                "body": body,
                "label": label,
                "types": [str(item) for item in types],
                "split": "base",
            }
        )
    return queries


def fetch_page(body, page, referer):
    payload = copy.deepcopy(body)
    payload["pagina"] = page
    data = request_json(API_URL, payload, referer)
    paging = data.get("paging") or {}
    postings = data.get("listPostings") or []
    first_id = postings[0].get("postingId") if postings else None
    return {
        "asked": page,
        "current": paging.get("currentPage"),
        "total": paging.get("total"),
        "total_pages": paging.get("totalPages") or 0,
        "postings": postings,
        "development_data": data.get("developmentData") or {},
        "first_id": first_id,
    }


def measure_cap(body, referer, failures):
    try:
        first = fetch_page(body, 1, referer)
    except Exception as error:
        failures.append(f"cap page 1: {error}")
        raise SystemExit(f"No se pudo leer la primera pagina de la API: {error}")
    if not first["postings"]:
        raise SystemExit("La primera pagina de la API no trajo avisos.")
    page1_id = first["first_id"]
    advertised = first["total_pages"]
    log(f"total anunciado {first['total']} en {advertised} paginas")

    def is_fresh(page):
        try:
            result = fetch_page(body, page, referer)
        except Exception as error:
            failures.append(f"cap page {page}: {error}")
            return False
        if result["current"] != page:
            return False
        if not result["postings"]:
            return False
        if page != 1 and result["first_id"] == page1_id:
            return False
        return True

    if advertised <= 1:
        return 1, first
    last_good = 1
    low = 2
    high = min(advertised, CAP_SEARCH_LIMIT)
    while low <= high:
        mid = (low + high) // 2
        if is_fresh(mid):
            last_good = mid
            low = mid + 1
        else:
            high = mid - 1
    log(f"tope de pagina con avisos nuevos: {last_good}")
    return last_good, first


def count_slice(body, referer, failures, label):
    try:
        result = fetch_page(body, 1, referer)
    except Exception as error:
        failures.append(f"{label}: {error}")
        return None
    return result


def price_bands(body, referer, failures, cap, usd_id, label):
    ceiling = 100_000

    def pages(min_price, max_price):
        probe = copy.deepcopy(body)
        probe["moneda"] = usd_id
        probe["preciomin"] = str(min_price)
        probe["preciomax"] = None if max_price is None else str(max_price)
        result = count_slice(probe, referer, failures, f"{label} precio {min_price}-{max_price}")
        if result is None:
            return None
        return result["total_pages"], result["total"]

    open_tail = pages(1, None)
    if open_tail is None:
        return []
    if open_tail[0] <= cap:
        return [(1, None, open_tail[1])]
    while True:
        tail = pages(ceiling, None)
        if tail is None:
            return []
        if tail[0] <= cap or ceiling >= 50_000_000:
            break
        ceiling *= 2

    cuts = [1]
    while True:
        remaining = pages(cuts[-1], None)
        if remaining is None:
            return []
        if remaining[0] <= cap:
            break
        left = cuts[-1] + 1
        right = ceiling
        best = None
        while left <= right:
            mid = (left + right) // 2
            band = pages(cuts[-1], mid)
            if band is None:
                return []
            if band[0] <= cap:
                best = mid
                left = mid + 1
            else:
                right = mid - 1
        if best is None or best <= cuts[-1]:
            cuts.append(cuts[-1] + 1)
        else:
            cuts.append(best)
        if len(cuts) > 40:
            break

    bands = []
    for index, start in enumerate(cuts):
        end = cuts[index + 1] if index + 1 < len(cuts) else None
        counted = pages(start, end)
        total = counted[1] if counted else None
        bands.append((start, end, total))
    return bands


def split_query(query, referer, failures, cap, usd_id, other_currency_ids):
    body = query["body"]
    label = query["label"]
    if query["split"] == "base" and len(query["types"]) > 1:
        children = []
        for type_id in query["types"]:
            child_body = copy.deepcopy(body)
            child_body["tipoDePropiedad"] = type_id
            children.append({**query, "body": child_body, "label": f"{label} tipo {type_id}", "split": "type"})
        return children

    if query["split"] != "price":
        children = []
        for start, end, _total in price_bands(body, referer, failures, cap, usd_id, label):
            child_body = copy.deepcopy(body)
            child_body["moneda"] = usd_id
            child_body["preciomin"] = str(start)
            child_body["preciomax"] = None if end is None else str(end)
            end_label = "o mas" if end is None else str(end)
            children.append(
                {
                    **query,
                    "body": child_body,
                    "label": f"{label} usd {start}-{end_label}",
                    "split": "price",
                }
            )
        unpriced = copy.deepcopy(body)
        unpriced["preciomin"] = None
        unpriced["preciomax"] = "0"
        unpriced["moneda"] = ""
        children.append({**query, "body": unpriced, "label": f"{label} sin precio", "split": "price"})
        for currency_id in other_currency_ids:
            other = copy.deepcopy(body)
            other["moneda"] = currency_id
            other["preciomin"] = "1"
            other["preciomax"] = None
            children.append(
                {
                    **query,
                    "body": other,
                    "label": f"{label} moneda {currency_id}",
                    "split": "price",
                }
            )
        return children
    return []


def feature_map(posting):
    found = {}
    for group_name in ("mainFeatures", "generalFeatures", "developmentFeatures"):
        group = posting.get(group_name) or {}
        if not isinstance(group, dict):
            continue
        for feature in group.values():
            if isinstance(feature, dict) and feature.get("label"):
                found.setdefault(norm(feature["label"]), feature)
    return found


def feature_value(features, *labels):
    for label in labels:
        feature = features.get(label)
        if feature and feature.get("value") not in (None, ""):
            return feature
    return None


def surface(features, label):
    feature = feature_value(features, label)
    if not feature:
        return "", "", ""
    raw = f"{feature.get('value')} {feature.get('measure') or ''}".strip()
    if is_square_meters(feature.get("measure")):
        return number_cell(parse_number(feature.get("value"))), raw, "aviso"
    return "", raw, ""


def location_names(posting):
    node = (posting.get("postingLocation") or {}).get("location") or {}
    names = {}
    barrio_id = ""
    while node:
        label = norm(node.get("label") or "")
        name = node.get("name") or ""
        if label and name and label not in names:
            names[label] = name
        if label == "barrio" and not barrio_id:
            barrio_id = node.get("locationId") or ""
        node = node.get("parent") or {}
        if not node:
            break
    address = (posting.get("postingLocation") or {}).get("address") or {}
    geo = ((posting.get("postingLocation") or {}).get("postingGeolocation") or {}).get("geolocation") or {}
    return {
        "barrio": names.get("barrio", ""),
        "zona": names.get("zona", ""),
        "ciudad": names.get("ciudad", ""),
        "barrio_id": barrio_id,
        "direccion": address.get("name") or "",
        "direccion_visibilidad": address.get("visibility") or "",
        "latitud": number_cell(geo.get("latitude")),
        "longitud": number_cell(geo.get("longitude")),
    }


def usd_amount(price):
    if not price:
        return None
    if price.get("currency") == "USD" or str(price.get("currencyId")) == "2":
        return parse_number(price.get("amount"))
    return None


def venta_prices(posting):
    prices = []
    for operation in posting.get("priceOperationTypes") or []:
        operation_type = (operation.get("operationType") or {}).get("operationTypeId")
        if operation_type not in (None, "1"):
            continue
        for price in operation.get("prices") or []:
            prices.append(price)
    return prices


def development_range(development_data, posting_id):
    data = {}
    if isinstance(development_data, dict):
        data = development_data.get(str(posting_id)) or development_data.get(posting_id) or {}
    minimum = ((data.get("minorPrices") or {}).get("tuple0") or {}) if isinstance(data, dict) else {}
    maximum = ((data.get("majorPrices") or {}).get("tuple0") or {}) if isinstance(data, dict) else {}
    return usd_amount(minimum), usd_amount(maximum)


def row_from_posting(posting, development_data):
    features = feature_map(posting)
    place = location_names(posting)
    prices = venta_prices(posting)
    usd_price = next((price for price in prices if usd_amount(price) is not None), None)
    shown = usd_price or (prices[0] if prices else None)
    precio_usd = usd_amount(usd_price)
    precio_min, precio_max = development_range(development_data, posting.get("postingId"))
    if precio_min is None and precio_usd is not None and posting.get("postingType") == "DEVELOPMENT":
        precio_min = precio_usd

    total_m2, total_raw, _total_origin = surface(features, "superficie total")
    covered_m2, covered_raw, _covered_origin = surface(features, "superficie cubierta")
    open_m2, open_raw, open_origin = surface(features, "superficie descubierta")
    if not open_m2:
        total_number = parse_number(total_m2)
        covered_number = parse_number(covered_m2)
        if total_number is not None and covered_number is not None and total_number >= covered_number:
            open_m2 = number_cell(total_number - covered_number)
            open_origin = "total_menos_cubierta"

    tipo_publicado = (posting.get("realEstateType") or {}).get("name") or ""
    tipo = TIPO.get(norm(tipo_publicado), "")
    rooms = feature_value(features, "ambientes", "ambiente")
    bedrooms = feature_value(features, "dormitorios", "dormitorio")
    baths = feature_value(features, "banos", "bano")
    toilets = feature_value(features, "toilettes", "toilette")
    garages = feature_value(features, "cocheras", "cochera")
    age = feature_value(features, "antiguedad")
    disposition = feature_value(features, "disposicion")
    orientation = feature_value(features, "orientacion")
    bright = feature_value(features, "luminoso")
    expenses = posting.get("expenses") or {}
    publisher = posting.get("publisher") or {}
    pictures = (posting.get("visiblePictures") or {}).get("pictures") or []
    extra_pictures = (posting.get("visiblePictures") or {}).get("additionalPicturesCount") or 0
    pill = posting.get("triggerPill") or ""
    path = posting.get("url") or ""
    url = path if path.startswith("http") else f"{ORIGIN}{path}"
    total_number = parse_number(total_m2)
    price_per_m2 = ""
    if precio_usd and total_number:
        price_per_m2 = number_cell(precio_usd / total_number)

    return {
        "id": posting.get("postingId") or "",
        "url": url,
        "titulo": posting.get("title") or posting.get("generatedTitle") or "",
        "precio_usd": number_cell(precio_usd),
        "precio_monto": number_cell(parse_number((shown or {}).get("amount"))),
        "precio_moneda": (shown or {}).get("currency") or "",
        "precio_texto": " ".join(
            part
            for part in ((shown or {}).get("formattedAmount"), (shown or {}).get("currency"))
            if part
        ),
        "precio_min_usd": number_cell(precio_min),
        "precio_max_usd": number_cell(precio_max),
        "precio_m2_usd": price_per_m2,
        "barrio": place["barrio"],
        "zona": place["zona"],
        "ciudad": place["ciudad"],
        "direccion": place["direccion"],
        "direccion_visibilidad": place["direccion_visibilidad"],
        "latitud": place["latitud"],
        "longitud": place["longitud"],
        "ambientes": number_cell(parse_number((rooms or {}).get("value"))),
        "dormitorios": number_cell(parse_number((bedrooms or {}).get("value"))),
        "banos": number_cell(parse_number((baths or {}).get("value"))),
        "toilettes": number_cell(parse_number((toilets or {}).get("value"))),
        "cocheras": number_cell(parse_number((garages or {}).get("value"))),
        "antiguedad": number_cell(parse_number((age or {}).get("value"))),
        "disposicion": (disposition or {}).get("value") or "",
        "orientacion": (orientation or {}).get("value") or "",
        "luminoso": (bright or {}).get("value") or "",
        "descripcion": clean_html(posting.get("descriptionNormalized")),
        "tipo": tipo,
        "tipo_publicado": tipo_publicado,
        "tipo_aviso": posting.get("postingType") or "",
        "superficie_total": total_m2,
        "superficie_cubierta": covered_m2,
        "superficie_descubierta": open_m2,
        "superficie_descubierta_origen": open_origin if open_m2 else "",
        "superficie_total_texto": total_raw,
        "superficie_cubierta_texto": covered_raw,
        "superficie_descubierta_texto": open_raw,
        "expensas": number_cell(parse_number(expenses.get("amount"))),
        "expensas_moneda": expenses.get("currency") or "",
        "anunciante": publisher.get("name") or "",
        "anunciante_id": publisher.get("publisherId") or "",
        "tipo_anunciante": PUBLISHER_TYPES.get(str(publisher.get("publisherTypeId") or ""), ""),
        "fecha_modificacion": posting.get("modified_date") or "",
        "reservado": "si" if posting.get("reserved") else "no",
        "estado": posting.get("status") or "",
        "apto_credito": "si" if "credito" in norm(pill) else ("no" if pill else ""),
        "tiene_video": "si" if posting.get("hasVideos") else "no",
        "tiene_tour": "si" if posting.get("hasTour") else "no",
        "tiene_planos": "si" if posting.get("hasPlans") else "no",
        "fotos": number_cell(len(pictures) + int(extra_pictures or 0)),
    }


def currencies_on_page(result):
    found = {}
    for posting in result["postings"]:
        for price in venta_prices(posting):
            currency_id = str(price.get("currencyId") or "")
            currency = price.get("currency") or ""
            if currency_id:
                found[currency_id] = currency
    return found


def download_slice(query, referer, cap):
    """Walk one slice on this thread's own session. Concurrent page requests overlap."""
    label = query["label"]
    local_failures = []
    local_rows = {}
    try:
        first = fetch_page(query["body"], 1, referer)
    except Exception as error:
        return {}, [f"{label} pagina 1: {error}"]
    total_pages = first["total_pages"]
    last_page = min(total_pages, cap)
    log(f"{label}: {first['total']} avisos, paginas {total_pages}, bajo {last_page}")
    seen_first = set()
    kept_pages = 0
    repeated = 0

    def fresh(result):
        if result is None or result["current"] != result["asked"] or not result["postings"]:
            return False
        return result["first_id"] not in seen_first

    for page in range(1, last_page + 1):
        result = first if page == 1 else None
        if page != 1:
            for _attempt in range(RETRIES):
                try:
                    result = fetch_page(query["body"], page, referer)
                except Exception as error:
                    local_failures.append(f"{label} pagina {page}: {error}")
                    result = None
                    continue
                if fresh(result):
                    break
        if not fresh(result):
            repeated += 1
            if repeated >= 3:
                log(f"{label}: las paginas dejan de traer avisos nuevos en {page}")
                break
            continue
        repeated = 0
        seen_first.add(result["first_id"])
        kept_pages += 1
        for posting in result["postings"]:
            record = row_from_posting(posting, result["development_data"])
            if record["id"]:
                local_rows[record["id"]] = record
        if kept_pages % 40 == 0:
            log(f"{label}: pagina {page}, avisos de este corte {len(local_rows)}")
    log(f"{label}: paginas {kept_pages}, avisos {len(local_rows)} de {first['total']}")
    return local_rows, local_failures


def collect_leaves(query, referer, cap, failures, usd_id, other_currency_ids, leaves):
    try:
        preview = fetch_page(query["body"], 1, referer)
    except Exception as error:
        failures.append(f"{query['label']} preview: {error}")
        log(f"fallo {query['label']}: {error}")
        return
    if preview["total_pages"] > cap:
        children = split_query(query, referer, failures, cap, usd_id, other_currency_ids)
        useful = []
        for child in children:
            counted = count_slice(child["body"], referer, failures, child["label"])
            if counted is None or not counted["total"]:
                continue
            if (
                counted["total_pages"] >= preview["total_pages"]
                and counted["total"] >= preview["total"] * 0.98
            ):
                log(f"{child['label']} no achica el corte ({counted['total']}), lo salto")
                continue
            if child["split"] == "price" and counted["total_pages"] > cap:
                log(f"{child['label']} sigue sobre el tope ({counted['total_pages']} paginas), lo salto")
                continue
            useful.append(child)
        if useful:
            for child in useful:
                collect_leaves(child, referer, cap, failures, usd_id, other_currency_ids, leaves)
            return
    leaves.append(query)


def output_path(url):
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".html"):
        name = name[: -len(".html")]
    if not name:
        name = "zonaprop"
    return Path("data") / f"{name}.csv"


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for posting_id in sorted(rows):
            writer.writerow(rows[posting_id])


def main():
    parser = argparse.ArgumentParser(description="Descarga un listado de ZonaProp a un CSV.")
    parser.add_argument("url", help="URL de la busqueda")
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Cortes que se bajan a la vez. Cada corte recorre sus paginas en su propia sesion",
    )
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers tiene que ser al menos 1")

    try:
        page = request(args.url, accept="text/html", referer=args.url).decode("utf-8", errors="replace")
    except Exception as error:
        raise SystemExit(f"No se pudo abrir la busqueda: {error}")
    state = load_state(page)
    if not state or not (state.get("listStore") or {}).get("listPostings"):
        raise SystemExit("La pagina no trajo el listado. Puede ser un desafio de verificacion.")

    queries = bodies_from_state(state)
    failures = []
    # Relevance repeats listings from one page to the next, so a walk cannot
    # cover the search. Most-recent is the same filter set in an order that
    # keeps pages apart, and it announces the same total.
    announced_body = copy.deepcopy(queries[0]["body"])
    for query in queries:
        query["body"]["sort"] = "more_recent"
    cap, _first = measure_cap(queries[0]["body"], args.url, failures)
    currency_page = count_slice(queries[0]["body"], args.url, failures, "monedas")
    currencies = currencies_on_page(currency_page) if currency_page else {}
    low_price = copy.deepcopy(queries[0]["body"])
    low_price["sort"] = "low_price"
    cheap_page = count_slice(low_price, args.url, failures, "monedas baratas")
    if cheap_page:
        currencies.update(currencies_on_page(cheap_page))
    usd_id = next((currency_id for currency_id, name in currencies.items() if name == "USD"), "2")
    other_currency_ids = [currency_id for currency_id, name in currencies.items() if name != "USD"]
    announced_page = count_slice(announced_body, args.url, failures, "total anunciado")
    announced = announced_page["total"] if announced_page else (currency_page["total"] if currency_page else None)

    # Past roughly this many pages, later pages repeat listings already seen.
    split_cap = min(cap, 140)
    log(f"corto cada busqueda en {split_cap} paginas")
    leaves = []
    for query in queries:
        collect_leaves(query, args.url, split_cap, failures, usd_id, other_currency_ids, leaves)
    log(f"cortes {len(leaves)}")
    for query in leaves:
        log(f"corte {query['label']}")
    rows = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        downloads = [pool.submit(download_slice, query, args.url, cap) for query in leaves]
        for download in as_completed(downloads):
            slice_rows, slice_failures = download.result()
            failures.extend(slice_failures)
            for posting_id, record in slice_rows.items():
                rows.setdefault(posting_id, record)
            log(f"acumulado {len(rows)}")

    path = output_path(args.url)
    write_csv(path, rows)
    log(f"archivo {path.resolve()}")
    log(f"filas {len(rows)}")
    log(f"total anunciado {announced}")
    log(f"paginas fallidas {len(failures)}")
    if failures:
        for failure in failures[:20]:
            log(f"fallo {failure}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

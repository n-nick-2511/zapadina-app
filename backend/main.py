from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from dotenv import load_dotenv
import time
import threading
import os
import requests
import math
from fastapi import BackgroundTasks
from ultralytics import YOLO
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ultralytics.utils.plotting import Annotator
import cv2

print("запуск файла:", __file__)
BASE_DIR = Path(__file__).resolve().parent

# --- инициализация приложения ---
app = FastAPI()

# --- подключение фронтенда ---
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR.parent / "frontend" / "static"),
    name="static"
)

# --- debug-доступ к файлам сервера ---
app.mount(
    "/debug",
    StaticFiles(directory="."),
    name="debug"
)

# --- переменные состояния сервера ---
last_ping = time.time()

processing = False
cancel_requested = False

status = {
    "stage": "idle",
    "current": 0,
    "total": 0
}

# --- настройка CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- модель YOLO (ленивая загрузка) ---
model = None

def get_model():
    global model

    model_path = BASE_DIR / "best1.pt"

    # загружаем модель один раз
    if model is None:
        model = YOLO(model_path)

    return model

# --- перевод координат в тайлы ---
def deg2num(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom

    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)

    return xtile, ytile

# --- подключение к базе данных ---
load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

# --- проверка "живости" сервера ---
@app.get("/ping")
def ping():
    global last_ping
    last_ping = time.time()
    return {"status": "ok"}

# --- отдача главной страницы ---
@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "../frontend/index.html"))

# --- получение всех детекций (GeoJSON) ---
@app.get("/api/detections")
def get_detections():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT json_build_object(
              'type', 'FeatureCollection',
              'features', COALESCE(json_agg(
                json_build_object(
                  'type', 'Feature',
                  'geometry', ST_AsGeoJSON(polygon)::json,
                  'properties', json_build_object(
                    'id', id,
                    'confidence', confidence
                  )
                )
              ), '[]'::json)
            )
            FROM detections;
    """)

    result = cur.fetchone()[0]

    if result["features"] is None:
        result["features"] = []

    cur.close()
    conn.close()

    return result

# --- экспорт всех детекций в KML ---
@app.get("/api/detections/kml/all")
def download_all_kml():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT ST_AsKML(polygon) FROM detections;")
    rows = cur.fetchall()

    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
    """

    for row in rows:
        kml += f"""
        <Placemark>
            {row[0]}
        </Placemark>
        """

    kml += "</Document></kml>"

    cur.close()
    conn.close()

    return Response(
        content=kml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={
            "Content-Disposition": "attachment; filename=all_detections.kml"
        }
    )

# --- экспорт KML по bbox ---
@app.get("/api/kml")
def download_kml(minLon: float, minLat: float, maxLon: float, maxLat: float):

    # подключаемся к БД
    conn = get_connection()
    cur = conn.cursor()

    # получаем детекции из выделенной части карты
    cur.execute("""
        SELECT ST_AsKML(polygon)
        FROM detections
        WHERE polygon IS NOT NULL
        AND ST_Intersects(
            polygon,
            ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        );
    """, (minLon, minLat, maxLon, maxLat))

    rows = cur.fetchall()

    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
    """

    for row in rows:
        kml += f"""
        <Placemark>
            {row[0]}
        </Placemark>
        """

    kml += "</Document></kml>"

    cur.close()
    conn.close()

    return Response(
        content=kml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={
            "Content-Disposition": "attachment; filename=detections.kml"
        }
    )

# --- скачивание тайла ---
def download_tile(x, y, z, save_dir):

    # формируем URL тайла
    url = f"https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"

    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"{x}_{y}.png")

    if os.path.exists(path):
        return path

    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except:
        return None

# --- получение тайлов по bbox ---
def get_tiles_in_bbox(bbox, zoom=15):
    min_lon, min_lat, max_lon, max_lat = bbox

    x1, y1 = deg2num(min_lat, min_lon, zoom)
    x2, y2 = deg2num(max_lat, max_lon, zoom)

    tiles = []

    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            tiles.append((x, y))

    return tiles

# --- перевод тайла в геокоординаты ---
def tile_bounds(x, y, z):
    n = 2.0 ** z

    lon1 = x / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    lon2 = (x + 1) / n * 360.0 - 180.0
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))

    return lon1, lat1, lon2, lat2

# --- сохранение детекции в БД ---
def save_detection_from_tile(x, y, xyxy, conf, zoom=15):

    lon1, lat1, lon2, lat2 = tile_bounds(x, y, zoom)

    tile_size = 256
    x1, y1, x2, y2 = xyxy

    min_lon = lon1 + (x1 / tile_size) * (lon2 - lon1)
    max_lon = lon1 + (x2 / tile_size) * (lon2 - lon1)

    max_lat = lat1 - (y1 / tile_size) * (lat1 - lat2)
    min_lat = lat1 - (y2 / tile_size) * (lat1 - lat2)

    polygon = f"""
    POLYGON((
        {min_lon} {min_lat},
        {max_lon} {min_lat},
        {max_lon} {max_lat},
        {min_lon} {max_lat},
        {min_lon} {min_lat}
    ))
    """

    # сохранение в PostGIS
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO detections (polygon, confidence)
        VALUES (ST_GeomFromText(%s, 4326), %s)
    """, (polygon, conf))

    conn.commit()
    cur.close()
    conn.close()
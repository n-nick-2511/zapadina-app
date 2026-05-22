from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
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



print("🔥 THIS FILE IS RUNNING:", __file__)
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR.parent / "frontend" / "static"),
    name="static"
)
app.mount("/debug", StaticFiles(directory="/root/zapadina-app/backend"), name="debug")


last_ping = time.time()

processing = False
cancel_requested = False
status = {
    "stage": "idle",
    "current": 0,
    "total": 0
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


model = None

def get_model():
    global model

    model_path = BASE_DIR / ("best1"
                             ".pt")
    if model is None:
        model = YOLO(model_path)
    return model

def deg2num(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile
def get_connection():
    return psycopg2.connect(
        host="c831c-rw.db.pub.dbaas.postgrespro.ru",
        port=5432,
        database="dbstud",
        user="circles",
        password="pass_circle_2026"
    )

@app.get("/ping")
def ping():
    global last_ping
    last_ping = time.time()
    return {"status": "ok"}

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "../frontend/index.html"))

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

@app.get("/api/detections/kml/all")
def download_all_kml():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
           SELECT ST_AsKML(polygon)
           FROM detections;
       """)

    rows = cur.fetchall()

    kml = """<?xml version="1.0" encoding="UTF-8"?>
       <kml xmlns="http://www.opengis.net/kml/2.2">
       <Document>

       <Style id="outlineOnly">
           <LineStyle>
               <color>ff0000ff</color>
               <width>2</width>
           </LineStyle>
           <PolyStyle>
               <fill>0</fill>
               <outline>1</outline>
           </PolyStyle>
       </Style>
       """

    for row in rows:
        kml += f"""
           <Placemark>
               <styleUrl>#outlineOnly</styleUrl>
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

@app.get("/api/kml")
def download_kml(minLon: float, minLat: float, maxLon: float, maxLat: float):
    print("KML REQUEST:", minLon, minLat, maxLon, maxLat)
    conn = get_connection()
    cur = conn.cursor()

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

    <Style id="outlineOnly">
        <LineStyle>
            <color>ff0000ff</color>
            <width>2</width>
        </LineStyle>
        <PolyStyle>
            <fill>0</fill>
            <outline>1</outline>
        </PolyStyle>
    </Style>
    """

    for row in rows:
        kml += f"""
        <Placemark>
            <styleUrl>#outlineOnly</styleUrl>
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

def download_tile(x, y, z, save_dir):
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

def get_tiles_in_bbox(bbox, zoom=15):
    min_lon, min_lat, max_lon, max_lat = bbox

    x1, y1 = deg2num(min_lat, min_lon, zoom)
    x2, y2 = deg2num(max_lat, max_lon, zoom)

    print("DEBUG bbox:", bbox)
    print("DEBUG tiles range:")
    print("x:", x1, "→", x2)
    print("y:", y1, "→", y2)


    tiles = []

    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            print(f"tile: {x}, {y}")
            tiles.append((x, y))

    return tiles
def tile_bounds(x, y, z):
    n = 2.0 ** z

    lon1 = x / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    lon2 = (x + 1) / n * 360.0 - 180.0
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))

    return lon1, lat1, lon2, lat2


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

    print("polygon:", polygon)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO detections (polygon, confidence)
        VALUES (ST_GeomFromText(%s, 4326), %s)
    """, (polygon, conf))

    conn.commit()
    cur.close()
    conn.close()


def process_area(bbox):
    global status, cancel_requested, processing

    print(" process_area START", bbox)

    processing = True
    cancel_requested = False

    tiles = get_tiles_in_bbox(bbox)
    total = len(tiles)

    status = {
        "stage": "downloading",
        "current": 0,
        "total": total
    }

    paths = []

    try:
        # 🔽 СКАЧИВАНИЕ
        for i, (x, y) in enumerate(tiles, start=1):

            if cancel_requested:
                status["stage"] = "cancelled"
                print(" Cancel during downloading")
                return

            path = download_tile(x, y, 15, "temp_tiles")

            if path:
                paths.append((path, x, y))

            status["current"] = i

        # 🔽 ДЕТЕКЦИЯ
        status["stage"] = "detecting"
        status["current"] = 0
        status["total"] = len(paths)

        model = get_model()

        for i, (tile_path, x, y) in enumerate(paths, start=1):

            if cancel_requested:
                status["stage"] = "cancelled"
                print("Cancel during detecting")
                return

            results = model.predict(tile_path, conf=0.2, imgsz=512)

            img = cv2.imread(tile_path)
            annotator = Annotator(img)

            for r in results:
                for box in r.boxes:
                    xyxy = box.xyxy[0].tolist()
                    conf = float(box.conf[0])

                    annotator.box_label(xyxy, f"{conf:.2f}")
                    save_detection_from_tile(x, y, xyxy, conf)

            img_out = annotator.result()

            out_path = os.path.join(BASE_DIR, f"debug_{x}_{y}.jpg")
            cv2.imwrite(out_path, img_out)

            status["current"] = i

        status["stage"] = "done"
        print("✅ process_area DONE")

    finally:
        import shutil
        shutil.rmtree("temp_tiles", ignore_errors=True)

        processing = False



@app.post("/api/cancel")
def cancel():
    global cancel_requested
    cancel_requested = True
    return {"status": "cancelling"}

@app.get("/api/status")
def get_status():
    global status, processing
    return {
        "processing": processing,
        **status
    }
@app.post("/api/run-detection")
def run_detection(data: dict, background_tasks: BackgroundTasks):
    global processing

    if processing:
        return {"status": "already running"}

    bbox = data["bbox"]

    print("Получен bbox:", bbox)

    background_tasks.add_task(process_area, bbox)

    return {"status": "started"}


@app.delete("/api/detections/{det_id}")
def delete_detection(det_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM detections
        WHERE id = %s
    """, (det_id,))

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok"}



def watchdog():
    global last_ping

    while True:
        time.sleep(5)

        if time.time() - last_ping > 10000:
            print("Выключаем сервер")
            os._exit(0)

threading.Thread(target=watchdog, daemon=True).start()
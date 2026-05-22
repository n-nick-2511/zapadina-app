document.addEventListener("DOMContentLoaded", function () {

let REGIONS = {};
let currentRegion = null;


var map = L.map('map', {
    zoomControl: false
}).setView([52.55, 42.58], 10);

//map.on('draw:drawstart', function () {
//    document.querySelectorAll('.leaflet-draw-tooltip')
//        .forEach(el => el.remove());
//});
// +/- на карте
L.control.zoom({
    position: 'topright'
}).addTo(map);

//const geocoder = L.Control.geocoder({
//    defaultMarkGeocode: true,
//    collapsed: true,
//    placeholder: "Поиск..."
//}).addTo(map);

//const searchControl = L.control({ position: "topleft" });
//
//searchControl.onAdd = function () {
//
//    const div = L.DomUtil.create("div", "leaflet-bar leaflet-control");
//
//    const a = L.DomUtil.create("a", "", div);
//    a.innerHTML = "🔍";
//    a.href = "#";
//    a.title = "Поиск";
//
//    L.DomEvent.disableClickPropagation(div);
//
//    L.DomEvent.on(a, "click", function (e) {
//        e.preventDefault();
//
//        const geocoderBtn = document.querySelector(".leaflet-control-geocoder-icon");
//
//        if (geocoderBtn) {
//            geocoderBtn.click();
//        } else {
//            console.warn("geocoder button not found");
//        }
//    });
//
//    return div;
//};
//
//searchControl.addTo(map);



const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

L.drawLocal.draw.handlers.rectangle.tooltip.start = "";
L.drawLocal.draw.handlers.rectangle.tooltip.cont = "";
L.drawLocal.draw.handlers.rectangle.tooltip.actions = "";
L.drawLocal.draw.handlers.simpleshape.tooltip.end = "";
L.drawLocal.draw.toolbar.buttons.rectangle = '';

L.drawLocal.draw.toolbar.actions.text = '';
L.drawLocal.draw.toolbar.actions.title = '';

const drawControl = new L.Control.Draw({
    position: 'topleft',

    draw: {
        polygon: false,
        polyline: false,
        circle: false,
        circlemarker: false,
        marker: false,
        rectangle: true
    }
});

L.drawLocal.draw.toolbar.actions = {};

map.addControl(drawControl);

const downloadControl = L.Control.extend({

    options: {
        position: 'topleft'
    },

    onAdd: function () {

        const container = L.DomUtil.create(
            'div',
            'leaflet-bar leaflet-control'
        );

        container.innerHTML = `
            <a href="#"
               title="Скачать все детекции в KML"
               id="downloadKMLControl">
               ⭳
            </a>
        `;

        L.DomEvent.disableClickPropagation(container);

        container.onclick = function(e) {
            e.preventDefault();
            downloadKML();
        };

        return container;
    }
});

map.addControl(new downloadControl());

//L.drawLocal.draw.toolbar.actions.title = "";
//L.drawLocal.draw.toolbar.actions.text = "";
//L.drawLocal.draw.handlers.rectangle.tooltip.start = "";

document.querySelector('.leaflet-draw-draw-rectangle')
    .title = "Выделить область";

map.on(L.Draw.Event.CREATED, function (e) {

    if (window.selectedLayer) {
            map.removeLayer(window.selectedLayer);
        }

    drawnItems.clearLayers();

    const layer = e.layer;
    drawnItems.addLayer(layer);

    const bounds = layer.getBounds();

    const bbox = [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth()
    ];

    console.log("BBOX:", bbox);

    // popup с кнопками
    layer.bindPopup(`
        <b>Выделен участок</b><br><br>
        <button onclick="runDetection()">Запустить детекцию</button><br><br>
        <button onclick="downloadSelectedKML()">Скачать KML</button><br><br>
        <button onclick="cancelSelection()">Отмена</button>
    `).openPopup();

    // сохраняем bbox глобально
    window.selectedBBox = bbox;
    window.selectedLayer = layer;
});

// спутник + подписи
L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
    maxZoom: 20,
    opacity: 0.8
}).addTo(map);



var geojsonLayer = L.geoJSON(null, {


    style: {
        color: "red",
        weight: 2,
        fillOpacity: 0.0
    },

    onEachFeature: function (feature, layer) {
        let conf = feature.properties?.confidence;

        if (conf !== undefined && conf !== null) {
            layer.bindTooltip(
                `confidence: ${conf.toFixed(2)}`,
                {
                    sticky: true,
                    direction: "top",
                    opacity: 0.9
                }
            );
        }


        // =========================
        //  DELETE ON CLICK
        // =========================
        layer.on("click", function () {

            const id = feature.properties?.id;

            if (!id) {
                console.warn("No ID in feature:", feature);
                return;
            }

            const modal = document.getElementById("confirmModal");

            modal.classList.remove("hidden");

            document.getElementById("confirmYes").onclick = function () {

                fetch(`/api/detections/${id}`, {
                    method: "DELETE"
                })
                .then(() => {
                    geojsonLayer.removeLayer(layer);
                    modal.classList.add("hidden");
                });

            };

            document.getElementById("confirmNo").onclick = function () {
                modal.classList.add("hidden");
            };

        });
    }

}).addTo(map);




// сетка тайлов
//L.GridLayer.DebugCoords = L.GridLayer.extend({
//    createTile: function(coords) {
//        var tile = document.createElement('div');
//        tile.style.outline = '1px solid blue';
//        tile.style.fontSize = '10px';
//        tile.style.color = 'blue';
//        tile.innerHTML = `x: ${coords.x}<br>y: ${coords.y}<br>z: ${coords.z}`;
//        return tile;
//    }
//});
//map.addLayer(new L.GridLayer.DebugCoords());


function loadDetections() {
    fetch("/api/detections")
        .then(res => res.json())
        .then(data => {
            geojsonLayer.clearLayers();   // убираем старые объекты
            geojsonLayer.addData(data);   // рисуем новые
        });
}



function checkProcessingStatus() {

    const interval = setInterval(() => {

        fetch("/api/status")
        .then(res => res.json())
        .then(data => {

            const text = document.getElementById("processingText");
            const spinner = document.getElementById("processingSpinner");
            const cancelBtn = document.getElementById("cancelBtn");
            const showResultsBtn = document.getElementById("showResultsBtn");
            const closeBtn = document.getElementById("closeProcessingWidget");



            if (data.stage === "downloading") {
                text.innerText = `Загрузка тайлов: ${data.current}/${data.total}`;
                spinner.style.display = "block";
                cancelBtn.style.display = "block";
                showResultsBtn.style.display = "none";
                closeBtn.style.display = "none";
            }

            if (data.stage === "detecting") {
                text.innerText = `Детекция: ${data.current}/${data.total}`;
                spinner.style.display = "block";
                cancelBtn.style.display = "block";
                showResultsBtn.style.display = "none";
                 closeBtn.style.display = "none";
            }

            if (data.stage === "done") {
                clearInterval(interval);

                text.innerText = "Готово";
                spinner.style.display = "none";
                cancelBtn.style.display = "none";
                showResultsBtn.style.display = "block";
            }

            if (data.stage === "cancelled") {
                clearInterval(interval);

                text.innerText = "Детекция отменена";
                spinner.style.display = "none";
                cancelBtn.style.display = "none";
                showResultsBtn.style.display = "none";
                closeBtn.style.display = "block";
            }

        });

    }, 1000);
}








function runDetection() {

    startProcessingUI();

    fetch("/api/run-detection", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ bbox: window.selectedBBox })
    })
    .then(res => res.json())
    .then(() => {

        // закрываем popup
        if (window.selectedLayer) {
            window.selectedLayer.closePopup();
            map.removeLayer(window.selectedLayer);
        }

        window.selectedBBox = null;

        // 🔥 ВАЖНО — начинаем слушать статус
        checkProcessingStatus();

    });
}






function cancelSelection() {

    if (window.selectedLayer) {
        map.removeLayer(window.selectedLayer);
    }

    drawnItems.clearLayers();

    window.selectedLayer = null;
    window.selectedBBox = null;
}

function startProcessingUI() {
    document.getElementById("processingWidget").style.display = "block";
    document.getElementById("processingSpinner").style.display = "block";
    document.getElementById("processingText").innerText = "Обработка...";
    document.getElementById("showResultsBtn").style.display = "none";
}

function finishProcessingUI() {
    document.getElementById("processingSpinner").style.display = "none";
    document.getElementById("processingText").innerText = "Готово ✅";
    document.getElementById("showResultsBtn").style.display = "block";
}


// ======================
// KML DOWNLOAD
// ======================

function downloadKML() {
    window.open(`/api/detections/kml/all`);
}

function downloadSelectedKML() {

    if (!window.selectedBBox) {
        alert("Сначала выдели область");
        return;
    }

    const bbox = window.selectedBBox;

    const url = `/api/kml?minLon=${bbox[0]}&minLat=${bbox[1]}&maxLon=${bbox[2]}&maxLat=${bbox[3]}`;

    console.log("KML URL:", url);

    window.open(url);
}

setInterval(() => {
    fetch("/ping")
        .catch(() => {});
}, 3000);




document.getElementById("showResultsBtn").onclick = function() {
    loadDetections(); // обновляем карту
    document.getElementById("processingWidget").style.display = "none";
};

document.getElementById("cancelBtn").onclick = function() {
    fetch("api/cancel", {
        method: "POST"
    });
};

document.getElementById("closeProcessingWidget").onclick = function() {
    document.getElementById("processingWidget").style.display = "none";
};

window.runDetection = runDetection;
window.cancelSelection = cancelSelection;
window.downloadKML = downloadKML;
window.downloadSelectedKML = downloadSelectedKML;


loadDetections();
});
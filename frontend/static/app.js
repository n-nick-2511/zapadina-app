document.addEventListener("DOMContentLoaded", function () {

    // глобальные переменные
    let REGIONS = {};
    let currentRegion = null;

    // инициализация карты
    var map = L.map('map', {
        zoomControl: false
    }).setView([52.55, 42.58], 10);

    // кнопки zoom (+/-)
    L.control.zoom({
        position: 'topright'
    }).addTo(map);

    // слой для выделенных объектов
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    // =========================
    // НАСТРОЙКА ИНСТРУМЕНТА ВЫДЕЛЕНИЯ
    // =========================

    L.drawLocal.draw.handlers.rectangle.tooltip.start = "";
    L.drawLocal.draw.handlers.rectangle.tooltip.cont = "";
    L.drawLocal.draw.handlers.rectangle.tooltip.actions = "";
    L.drawLocal.draw.handlers.simpleshape.tooltip.end = "";
    L.drawLocal.draw.toolbar.buttons.rectangle = '';

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

    map.addControl(drawControl);

    // =========================
    // КНОПКА СКАЧИВАНИЯ ВСЕХ KML
    // =========================

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
                   title="Скачать все детекции в KML">
                   ⭳
                </a>
            `;

            // отключаем перехват кликов картой
            L.DomEvent.disableClickPropagation(container);

            container.onclick = function(e) {
                e.preventDefault();
                downloadKML();
            };

            return container;
        }
    });

    map.addControl(new downloadControl());

    // подпись инструмента выделения
    document.querySelector('.leaflet-draw-draw-rectangle')
        .title = "Выделить область";

    // =========================
    // ОБРАБОТКА ВЫДЕЛЕНИЯ ОБЛАСТИ
    // =========================

    map.on(L.Draw.Event.CREATED, function (e) {

        // удаляем предыдущее выделение
        if (window.selectedLayer) {
            map.removeLayer(window.selectedLayer);
        }

        drawnItems.clearLayers();

        const layer = e.layer;
        drawnItems.addLayer(layer);

        const bounds = layer.getBounds();

        // формируем bbox
        const bbox = [
            bounds.getWest(),
            bounds.getSouth(),
            bounds.getEast(),
            bounds.getNorth()
        ];

        console.log("BBOX:", bbox);

        // popup с действиями
        layer.bindPopup(`
            <b>Выделен участок</b><br><br>
            <button onclick="runDetection()">Запустить детекцию</button><br><br>
            <button onclick="downloadSelectedKML()">Скачать KML</button><br><br>
            <button onclick="cancelSelection()">Отмена</button>
        `).openPopup();

        // сохраняем глобально
        window.selectedBBox = bbox;
        window.selectedLayer = layer;
    });

    // =========================
    // СЛОЙ КАРТЫ
    // =========================

    L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
        maxZoom: 20,
        opacity: 0.8
    }).addTo(map);

    // =========================
    // СЛОЙ ДЕТЕКЦИЙ
    // =========================

    var geojsonLayer = L.geoJSON(null, {

        style: {
            color: "red",
            weight: 2,
            fillOpacity: 0.0
        },

        onEachFeature: function (feature, layer) {

            // tooltip с confidence
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

            // обработка клика по объекту
            layer.on("click", function () {

                const id = feature.properties?.id;

                if (!id) {
                    console.warn("No ID in feature:", feature);
                    return;
                }

                const modal = document.getElementById("confirmModal");

                modal.classList.remove("hidden");

                // подтверждение удаления
                document.getElementById("confirmYes").onclick = function () {

                    fetch(`/api/detections/${id}`, {
                        method: "DELETE"
                    })
                    .then(() => {
                        geojsonLayer.removeLayer(layer);
                        modal.classList.add("hidden");
                    });

                };

                // отмена удаления
                document.getElementById("confirmNo").onclick = function () {
                    modal.classList.add("hidden");
                };

            });
        }

    }).addTo(map);

    // =========================
    // ЗАГРУЗКА ДЕТЕКЦИЙ
    // =========================

    function loadDetections() {
        fetch("/api/detections")
            .then(res => res.json())
            .then(data => {
                geojsonLayer.clearLayers();
                geojsonLayer.addData(data);
            });
    }

    // =========================
    // ОТСЛЕЖИВАНИЕ СТАТУСА ОБРАБОТКИ
    // =========================

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

                // загрузка тайлов
                if (data.stage === "downloading") {
                    text.innerText = `Загрузка: ${data.current}/${data.total}`;
                    spinner.style.display = "block";
                }

                // детекция
                if (data.stage === "detecting") {
                    text.innerText = `Детекция: ${data.current}/${data.total}`;
                }

                // завершено
                if (data.stage === "done") {
                    clearInterval(interval);
                    text.innerText = "Готово";
                    showResultsBtn.style.display = "block";
                }

                // отмена
                if (data.stage === "cancelled") {
                    clearInterval(interval);
                    text.innerText = "Отменено";
                    closeBtn.style.display = "block";
                }

            });

        }, 1000);
    }

    // =========================
    // ЗАПУСК ДЕТЕКЦИИ
    // =========================

    function runDetection() {

        startProcessingUI();

        fetch("/api/run-detection", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ bbox: window.selectedBBox })
        })
        .then(() => {

            if (window.selectedLayer) {
                window.selectedLayer.closePopup();
                map.removeLayer(window.selectedLayer);
            }

            window.selectedBBox = null;

            checkProcessingStatus();
        });
    }

    // =========================
    // ОТМЕНА ВЫДЕЛЕНИЯ
    // =========================

    function cancelSelection() {

        if (window.selectedLayer) {
            map.removeLayer(window.selectedLayer);
        }

        drawnItems.clearLayers();

        window.selectedLayer = null;
        window.selectedBBox = null;
    }

    // =========================
    // UI СОСТОЯНИЕ ОБРАБОТКИ
    // =========================

    function startProcessingUI() {
        document.getElementById("processingWidget").style.display = "block";
        document.getElementById("processingText").innerText = "Обработка...";
    }

    // =========================
    // СКАЧИВАНИЕ KML
    // =========================

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

        window.open(url);
    }

    // =========================
    // ПИНГ СЕРВЕРА, ПОДДЕРЖКА "ЖИВОСТИ"
    // =========================

    setInterval(() => {
        fetch("/ping").catch(() => {});
    }, 3000);

    // =========================
    // ОБРАБОТЧИКИ UI
    // =========================

    document.getElementById("showResultsBtn").onclick = function() {
        loadDetections();
        document.getElementById("processingWidget").style.display = "none";
    };

    document.getElementById("cancelBtn").onclick = function() {
        fetch("api/cancel", { method: "POST" });
    };

    document.getElementById("closeProcessingWidget").onclick = function() {
        document.getElementById("processingWidget").style.display = "none";
    };

    // экспорт функций в глобальную область
    window.runDetection = runDetection;
    window.cancelSelection = cancelSelection;
    window.downloadKML = downloadKML;
    window.downloadSelectedKML = downloadSelectedKML;

    // стартовая загрузка данных
    loadDetections();
});
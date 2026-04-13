// some parts of this script are helped written by github copilot
// but the overall structure and logic are manually implemented to fit the specific needs of this project

const { useEffect, useRef, useState } = React;

const RISK_LEVELS = [
  "No Data",
  "Lower Risk",
  "Caution",
  "Extreme Caution",
  "Danger",
  "Extreme Danger",
];

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function safeFixed(value, digits = 1, fallback = "—") {
  // guard against null or non-numeric api values during rerenders
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : fallback;
}
function safeDateLabel(value, options, fallback = "—") {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }
  return new Intl.DateTimeFormat("en-US", options).format(parsed);
}



function formatMapTime(value) {
  if (!value) {
    return "Map time: —";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Map time: —";
  }

  const parts = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Jakarta",
  }).formatToParts(parsed);

  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `Map time: ${byType.month} ${byType.day} ${byType.hour}:${byType.minute}`;
}

function PlotlyFigure({ figure, className }) {
  const containerRef = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || !figure) {
      return undefined;
    }

    setError(null);

    Plotly.newPlot(node, figure.data || [], figure.layout || {}, {
      displayModeBar: false,
      responsive: true,
    }).catch((plotError) => {
      console.error("Plotly render failed", plotError, figure);
      setError(plotError?.message || "Plotly render failed.");
    });

    const resizeHandler = () => {
      if (node.isConnected) {
        Plotly.Plots.resize(node);
      }
    };

    window.addEventListener("resize", resizeHandler);

    return () => {
      window.removeEventListener("resize", resizeHandler);
      if (node.isConnected) { // guard against re-render after unmount
        Plotly.purge(node); // clean up the plotly instance
      }
    };
  }, [figure]);


  return (
    <>
      {error && <div className="plot-error">{error}</div>}
      <div ref={containerRef} className={className} />
    </>
  );
}


// using leaflet for the map view
// more performant than plotly (I guess)
function LeafletMap({ geojson, config, className }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const [error, setError] = useState(null);
  const JAKARTA_CENTER = [-6.2088, 106.8456];
  const JAKARTA_BOUNDS = [
    [-6.42, 106.68],
    [-6.05, 107.03],
  ];

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return undefined;
    }

    try {
      //zooming init
      const map = L.map(containerRef.current, {
        zoomControl: true,
        attributionControl: true,
        maxBounds: JAKARTA_BOUNDS,
        maxBoundsViscosity: 0.85,
      }).setView(JAKARTA_CENTER, 10.5);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { // light carto map tiles
        attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;


      // leaflet sometimes needs an explicit size recalculation after react mounts the container(?)
      requestAnimationFrame(() => {
        map.invalidateSize();
      });
    } catch (mapError) {
      console.error("Leaflet init failed", mapError);
      setError(mapError?.message || "Leaflet init failed.");
    }

    return () => {
      if (layerRef.current) {
        layerRef.current.remove();
        layerRef.current = null;
      }
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !geojson) {
      return;
    }

    try {
      setError(null);
      if (layerRef.current) {
        layerRef.current.remove(); // replace the previous timestamp layer instead of stacking polygons
      }

      const layer = L.geoJSON(geojson, {
        style: (feature) => {
          const riskLevel = feature?.properties?.risk_level || "No Data";
          return {
            color: "rgba(70,70,70,0.85)",
            weight: 1,
            fillColor: config.riskColorMap[riskLevel] || "#dcdcdc",
            fillOpacity: 0.58,
          };
        },
        onEachFeature: (feature, leafletLayer) => {
          const props = feature.properties || {};
          const ward = props.desa_kelurahan || "No Data";
          const district = props.kecamatan || "";
          const timestamp = props.local_datetime || "—";
          const heatIndex = props.heat_index_c == null ? "—" : `${Number(props.heat_index_c).toFixed(1)} °C`;
          const riskLevel = props.risk_level || "No Data";
          const weather = props.weather_desc || "";

          leafletLayer.bindTooltip(
            `
              <div class="leaflet-tooltip-card">
                <div><strong>${ward}${district ? `, ${district}` : ""}</strong></div>
                <div>${timestamp}</div>
                <div>HI ${heatIndex} - ${riskLevel}</div>
                <div>${weather}</div>
              </div>
            `,
            { sticky: true }
          );
        },
      }).addTo(mapRef.current);

      layerRef.current = layer;
      mapRef.current.setView(JAKARTA_CENTER, 10.5); // reset view after each layer swap
      requestAnimationFrame(() => {
        if (mapRef.current) {
          mapRef.current.invalidateSize();
        }
      });
    } catch (mapError) {
      console.error("Leaflet layer failed", mapError, geojson);
      setError(mapError?.message || "Leaflet layer failed.");
    }
  }, [config.riskColorMap, geojson]);

  return (
    <>
      {error && <div className="plot-error">{error}</div>}
      <div ref={containerRef} className={className} />
    </>
  );
}


function Header({ pathname, lastDbUpdateDisplay, onNavigate }) {
  return (
    <header className="top-header">
      {/* <div className="header-brand">
        <span className="brand-accent">Jakarta</span>
        <span className="brand-main"> JKT Heat Risk</span>
      </div> */}

      <nav className="header-nav">
        <a
          href="/location"
          className={pathname === "/map" ? "nav-link" : "nav-link active"}
          onClick={(event) => onNavigate(event, "/location")}
        >
          Ward Info
        </a>
        <a
          href="/map"
          className={pathname === "/map" ? "nav-link active" : "nav-link"}
          onClick={(event) => onNavigate(event, "/map")}
        >
          Map Info
        </a>
      </nav>
      
      {/* from last fetched data */}
      <div className="header-meta">
        <span className="meta-label">DB last updated </span>
        <span className="meta-value">{lastDbUpdateDisplay || "—"}</span>
      </div>
    </header>
  );
}


function GuideSection({ riskColorMap, riskLabelMap, onOpen }) {
  const levels = RISK_LEVELS.slice(1);

  return (
    <div className="guide-section">
      <div className="sidebar-section-title">Heat Risk Guide</div>
      <p className="sidebar-caption">
        Based on the{" "}
        <a
          href="https://www.wpc.ncep.noaa.gov/heatrisk/"
          target="_blank"
          rel="noreferrer"
          className="inline-link"
        >
          U.S. National Weather Service
        </a>{" "}
        heat risk framework.
      </p>

      <div className="guide-list">
        {levels.map((level) => (
          <button
            key={level}
            type="button"
            className="guide-btn"
            onClick={() => onOpen(level)}
          >
            <span className="guide-item-left">
              <span
                className="risk-dot"
                style={{ background: riskColorMap[level] }}
              />
              <span className="guide-item-label">
                {riskLabelMap[level] || level}
              </span>
            </span>
            <span className="guide-item-cta">View →</span>
          </button>
        ))}
      </div>
    </div>
  );
}
function Sidebar({ config, onOpenGuide }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-inner">
        <GuideSection
          riskColorMap={config.riskColorMap}
          riskLabelMap={config.riskLabelMap}
          onOpen={onOpenGuide}
        />

        <hr className="sidebar-divider" />
        <div className="sidebar-section-title">About</div>
        <div className="sidebar-about">
          <p>
            Heat index is computed using the regression formula from the{" "}
            <a
              href="https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml"
              target="_blank"
              rel="noreferrer"
            >
              US National Weather Service
            </a>
            . The formula is calibrated for US sub-tropical conditions; accuracy
            for tropical regions like Indonesia is approximate, but sufficient
            as a first-order estimate.
          </p>
        </div>

        <div className="sidebar-about">
          <p>
            Weather data from BMKG&apos;s{" "}
            <a
              href="https://data.bmkg.go.id/prakiraan-cuaca/"
              target="_blank"
              rel="noreferrer"
            >
              Data Prakiraan Cuaca Terbuka
            </a>{" "}
            via free public API.
          </p>
        </div>
        <div className="sidebar-footer">
          <img src="/assets/github.svg" alt="" className="footer-icon" />
          <a
            href="https://github.com/salirafi/Jakarta-Heat-Risk-App"
            target="_blank"
            rel="noreferrer"
            className="footer-link"
          >
            Go to project repo
          </a>
        </div>
      </div>
    </aside>
  );
}


function GuideModal({ level, config, onClose }) {
  if (!level) {
    return <div className="modal-overlay" />;
  }

  const guide = config.heatRiskGuide[level];

  return (
    <div className="modal-overlay modal-show" onClick={onClose}>
      <div className="modal-box" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="modal-close-btn" onClick={onClose}>
          ×
        </button>
        <div className="modal-body">
          <div className="modal-header">
            <span
              className="risk-dot modal-risk-dot"
              style={{ background: config.riskColorMap[level] }}
            />
            <div>
              <div className="modal-risk-title">
                {config.riskLabelMap[level] || level}
              </div>
              <div className="modal-risk-sub">{guide.level}</div>
            </div>
          </div>
          <div className="modal-section">
            <div className="modal-section-label">What to expect</div>
            <div className="modal-section-text">{guide.expect}</div>
          </div>
          <div className="modal-section">
            <div className="modal-section-label">Recommended actions</div>
            <div className="modal-section-text">{guide.do}</div>
          </div>
        </div>
      </div>
    </div>
  );
}


// autocomplete search component for wards, used in the location page header
function WardSearch({ onSelect }) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const skipNextFetchRef = useRef(false); // flag to skip fetch after selection


  useEffect(() => {



    if (!query.trim()) {
      setOptions([]);
      return undefined;
    }

  
    // when an option is selected, set the query to the option label and skip the next fetch
    if (skipNextFetchRef.current) {
      skipNextFetchRef.current = false;
      setOptions([]);
      setOpen(false);
      return undefined;
    }

    const handle = window.setTimeout(async () => {
      try {
        const result = await fetchJson(`/api/wards?q=${encodeURIComponent(query)}`);
        setOptions(result);
        setOpen(true);
      } catch (_error) {
        setOptions([]);
      }
    }, 200); // debounce the api call by 200ms after user stops typing

    return () => window.clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    const handleClick = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="search-shell" ref={rootRef}>
      <div className="ward-search">
        <input
          type="text"
          value={query}
          className="ward-search-input"
          placeholder="Search ward…"
          onFocus={() => setOpen(options.length > 0)}
          onChange={(event) => {
            setQuery(event.target.value);
            if (!event.target.value.trim()) {
              onSelect(null);
            }
          }}
        />
        {query && (
          <button
            type="button"
            className="ward-search-clear"
            onClick={() => {
              setQuery("");
              setOptions([]);
              setOpen(false);
              onSelect(null);
            }}
          >
            ×
          </button>
        )}
      </div>

      {open && options.length > 0 && (
        <div className="ward-search-menu">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className="ward-search-option"
              onClick={() => {
                skipNextFetchRef.current = true;
                setQuery(option.label);
                setOpen(false);
                onSelect(option);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


function TimeMeta({ currentTimeDisplay, snapshotTimeDisplay }) {
  return (
    <div className="time-meta">
      <div className="time-meta-card">
        <div className="time-meta-label">Current Jakarta Time</div>
        <div className="time-meta-now">{currentTimeDisplay}</div>
        <div className="time-meta-data">
          <span className="time-meta-data-label">Forecast snapshot</span>
          <span className="time-meta-data-value">{snapshotTimeDisplay}</span>
        </div>
      </div>
    </div>
  );
}

function EmptyLocationState() {
  return (
    <div className="empty-state">
      <div className="empty-icon">🌡</div>
      <div className="empty-text">Select a ward to view heat risk data.</div>
    </div>
  );
}
function MetricsRow({ forecast, config }) {
  const row = forecast[0];
  if (!row) {
    return null;
  }

  return (
    <div className="metrics-row">
      <div className="metric-card">
        <div className="metric-label">Temperature</div>
        <div className="metric-value">{safeFixed(row.temperature_c)}°C</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Humidity</div>
        <div className="metric-value">{safeFixed(row.humidity_ptg)}%</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Heat Index</div>
        <div className="metric-value">{safeFixed(row.heat_index_c)}°C</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Risk Level</div>
        <div className="metric-value">
          {config.riskAbbr[row.risk_level] || row.risk_level}
        </div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Weather</div>
        <img
          className="weather-icon"
          src={`/assets/${config.weatherIconMap[row.weather_desc] || "cloudy.svg"}`} // default to cloudy icon if description is missing or unmapped
          alt={row.weather_desc || "Weather"}
        />
      </div>
    </div>
  );
}


function ForecastCards({ forecast, config }) {
  if (!forecast.length) {
    return <div className="empty-note">No available data.</div>;
  }

  return (
    <div className="forecast-scroll-wrap">
      <div className="forecast-scroll">
        {forecast.map((item) => (
          <div
            key={`${item.adm4}-${item.local_datetime}`}
            className="forecast-card"
            style={{
              background: hexToRgba(config.riskColorMap[item.risk_level] || "#dcdcdc", 0.15),
            }}
          >
            <div className="fc-ward">{item.desa_kelurahan}</div>
            <div className="fc-time">
              {safeDateLabel(item.local_datetime, {
                month: "short",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
                timeZone: "Asia/Jakarta",
              })}
            </div>
            <div className="fc-hi">HI: {safeFixed(item.heat_index_c)} °C</div>
            <div className="fc-risk">{riskBadge(item.risk_level)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LocationPage({ bootstrap, config }) {
  const [selectedWard, setSelectedWard] = useState(null);
  const [forecastState, setForecastState] = useState({
    forecast: [],
    current_time_display: bootstrap.runtime.current_jakarta_time_display,
    snapshot_time_display: "—",
    timeline_figure: null,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedWard) {
      setForecastState({
        forecast: [],
        current_time_display: bootstrap.runtime.current_jakarta_time_display,
        snapshot_time_display: "—",
        timeline_figure: null,
      });
      return undefined;
    }

    let active = true;
    setLoading(true);

    fetchJson(`/api/forecast?adm4=${encodeURIComponent(selectedWard.value)}`)
      .then((result) => {
        if (active) {
          setForecastState(result);
        }
      })
      .catch(() => {
        if (active) {
          setForecastState({
            forecast: [],
            current_time_display: bootstrap.runtime.current_jakarta_time_display,
            snapshot_time_display: "—",
            timeline_figure: null,
          });
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [bootstrap.runtime.current_jakarta_time_display, selectedWard]);

  return (
    <div className="right-panel">
      <div className="location-top-row">
        <TimeMeta
          currentTimeDisplay={forecastState.current_time_display}
          snapshotTimeDisplay={forecastState.snapshot_time_display}
        />

        <div className="search-bar-row">
          <WardSearch onSelect={setSelectedWard} />
        </div>
      </div>

      <div className="location-body">
        {!selectedWard && <EmptyLocationState />}

        {selectedWard && loading && !forecastState.forecast.length && (
          <div className="empty-note">Loading forecast…</div>
        )}

        {selectedWard && !loading && !forecastState.forecast.length && (
          <div className="empty-note">No data for the selected region.</div>
        )}

        {selectedWard && forecastState.forecast.length > 0 && (
          <>
            <MetricsRow forecast={forecastState.forecast} config={config} />

            <div className="forecast-section">
              <ForecastCards forecast={forecastState.forecast} config={config} />
            </div>

            <div className="evolution-section">
              <PlotlyFigure
                figure={forecastState.timeline_figure}
                className="plot-host plot-host-timeline"
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// map legend component¥
function MapLegend({ config }) {
  return (
    <div className="legend-container">
      <div className="legend-row">
        {RISK_LEVELS.map((level) => (
          <div key={level} className="legend-item">
            <span
              className="legend-dot"
              style={{ backgroundColor: config.riskColorMap[level] }}
            />
            <span className="legend-label">
              {config.riskLabelMap[level] || level}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SliderMarks({ forecastTimes, sliderMarks }) {
  if (!forecastTimes.length) {
    return null;
  }

  return (
    <div className="slider-marks">
      {Object.entries(sliderMarks).map(([index, label]) => {
        const left = forecastTimes.length === 1
          ? 0
          : (Number(index) / (forecastTimes.length - 1)) * 100;

        return (
          <div key={index} className="slider-mark" style={{ left: `${left}%` }}>
            {String(label).split("\n").map((part) => (
              <span key={part}>{part}</span>
            ))}
          </div>
        );
      })}
    </div>
  );
}


function MapPage({ bootstrap, config }) {
  const forecastTimes = bootstrap.runtime.forecast_times || [];
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [draftIdx, setDraftIdx] = useState(0);
  const [mapState, setMapState] = useState({
    geojson: null,
  });
  const [mapError, setMapError] = useState(null);

  const selectedTime = forecastTimes[selectedIdx] || "";
  const draftTime = forecastTimes[draftIdx] || "";

  useEffect(() => {
    // keep the visible thumb in sync when the committed timestamp changes elsewhere
    setDraftIdx(selectedIdx);
  }, [selectedIdx]);

  useEffect(() => {
    let active = true;
    setMapError(null);

    fetchJson(`/api/map-data?time=${encodeURIComponent(selectedTime)}`)
      .then((result) => {
        if (active) {
          setMapState(result);
        }
      })
      .catch(() => {
        if (active) {
          setMapError("Failed to load map layer data.");
          setMapState({
            geojson: null,
          });
        }
      });

    return () => {
      active = false;
    };
  }, [selectedTime]);

  const commitSliderValue = () => {
    setSelectedIdx(draftIdx); // commit on release so dragging does not trigger map fetches
  };

  return (
    <div className="right-panel right-panel-map">
      <div className="slider-row">
        <div className="map-time-caption">{formatMapTime(draftTime)}</div>
        <div className="slider-wrap">
          <input
            type="range"
            min="0"
            max={Math.max(forecastTimes.length - 1, 0)}
            step="1"
            value={draftIdx}
            className="map-slider"
            onChange={(event) => setDraftIdx(Number(event.target.value))}
            onMouseUp={commitSliderValue}
            onTouchEnd={commitSliderValue}
            onKeyUp={(event) => {
              if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                commitSliderValue();
              }
            }}
          />
          <SliderMarks
            forecastTimes={forecastTimes}
            sliderMarks={bootstrap.runtime.slider_marks || {}}
          />
        </div>
      </div>

      <div className="map-content-row">
        <div className="map-section map-section-full">
          {mapError && <div className="plot-error">{mapError}</div>}
          <LeafletMap
            geojson={mapState.geojson}
            config={config}
            className="plot-host plot-host-map leaflet-host"
          />
          <MapLegend config={config} />
        </div>
      </div>
    </div>
  );
}


function App() {
  const [bootstrap, setBootstrap] = useState(null);
  const [pathname, setPathname] = useState(window.location.pathname || "/location");
  const [activeGuide, setActiveGuide] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;

    fetchJson("/api/bootstrap")
      .then((result) => {
        if (active) {
          setBootstrap(result);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(loadError.message || "Failed to load app data.");
        }
      });

    const handlePopState = () => {
      setPathname(window.location.pathname || "/location");
    };

    window.addEventListener("popstate", handlePopState);
    return () => {
      active = false;
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  if (error) {
    return (
      <div className="app-shell">
        <div className="page-body">
          <main className="main-content">
            <div className="right-panel">
              <div className="empty-state">
                <div className="empty-text">{error}</div>
              </div>
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (!bootstrap) {
    return (
      <div className="app-shell">
        <div className="page-body">
          <main className="main-content">
            <div className="right-panel">
              <div className="empty-state">
                <div className="empty-text">Loading app…</div>
              </div>
            </div>
          </main>
        </div>
      </div>
    );
  }



  const normalizedPath = pathname === "/" ? "/location" : pathname;
  const onNavigate = (event, nextPath) => {
    event.preventDefault();
    if (nextPath === pathname) {
      return;
    }

    window.history.pushState({}, "", nextPath);
    setPathname(nextPath);
  };

  return (
    <div className="app-shell">
      <Header
        pathname={normalizedPath}
        lastDbUpdateDisplay={bootstrap.runtime.last_db_update_display}
        onNavigate={onNavigate}
      />

      <div className="page-body">
        <Sidebar config={bootstrap.config} onOpenGuide={setActiveGuide} />

        <main className="main-content">
          {normalizedPath === "/map" ? (
            <MapPage bootstrap={bootstrap} config={bootstrap.config} />
          ) : (
            <LocationPage bootstrap={bootstrap} config={bootstrap.config} />
          )}
        </main>
      </div>

      <GuideModal
        level={activeGuide}
        config={bootstrap.config}
        onClose={() => setActiveGuide(null)}
      />
    </div>
  );
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    // swap the app shell for a safe fallback ui if any child render crashes
    return {
      hasError: true,
      message: error?.message || "The app hit a runtime error.",
    };
  }

  componentDidCatch(error, info) {
    console.error("React runtime error", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-shell">
          <div className="page-body">
            <main className="main-content">
              <div className="right-panel">
                <div className="empty-state">
                  <div className="empty-text">{this.state.message}</div>
                </div>
              </div>
            </main>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

function riskBadge(level) {
  if (level === "Extreme Danger") {
    return "🚨 Extreme Danger";
  }
  if (level === "Danger") {
    return "🔴 Danger";
  }
  if (level === "Extreme Caution") {
    return "🟠 Extreme Caution";
  }
  if (level === "Caution") {
    return "🟡 Caution";
  }
  if (level === "Lower Risk") {
    return "🟢 Lower Risk";
  }
  return "⚪ No Data";
}



// convert hex color to rgba with specified alpha/opacity
function hexToRgba(hexColor, alpha) {
  const color = String(hexColor || "").replace("#", "");
  if (color.length !== 6) {
    return `rgba(220,220,220,${alpha})`;
  }

  const r = parseInt(color.slice(0, 2), 16);
  const g = parseInt(color.slice(2, 4), 16);
  const b = parseInt(color.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);

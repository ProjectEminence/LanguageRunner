// Custom matchers for DOM assertions (e.g. toBeInTheDocument)
require('@testing-library/jest-dom');

// jsdom's window.scrollTo throws "Not implemented" (e.g. Details.tsx uses it)
if (typeof window !== 'undefined') {
  window.scrollTo = () => {};
}

// ---- Visualization libraries ----

// Highcharts
try {
jest.mock("highcharts", () => ({
  chart: jest.fn(),
  stockChart: jest.fn(),
  mapChart: jest.fn(),
  series: [],
}));
} catch (error) {
  console.info("Just for info mocking highcharts: highcharts is not installed");
}

try {
  // Chart.js
  jest.mock("chart.js", () => ({
    Chart: jest.fn(),
  }));
} catch (error) {
  console.info("Just for info mocking chart.js: chart.js is not installed");
}

// Plotly.js / react-plotly.js — full lib expects browser globals (self, window, canvas, createObjectURL)
try {
  jest.mock("plotly.js", () => ({
    newPlot: jest.fn(),
    react: jest.fn(),
    purge: jest.fn(),
  }));
  jest.mock("react-plotly.js", () => ({
    __esModule: true,
    default: function PlotMock() {
      return null;
    },
  }));
} catch (error) {
  console.info("Just for info mocking plotly: plotly is not installed");
}

try {
  // ECharts
  jest.mock("echarts", () => ({
    init: jest.fn(() => ({
      setOption: jest.fn(),
      resize: jest.fn(),
      dispose: jest.fn(),
    })),
  }));
} catch (error) {
  console.info("Just for info mocking echarts: echarts is not installed");
}

// ---- Map libraries ----

try {
  // Mapbox-gl
  jest.mock("mapbox-gl", () => ({
    Map: jest.fn(() => ({
      on: jest.fn(),
      remove: jest.fn(),
    })),
  }));
} catch (error) {
  console.info("Just for info mocking mapbox-gl: mapbox-gl is not installed");
}

try {
// Leaflet
jest.mock("leaflet", () => ({
  map: jest.fn(() => ({
    setView: jest.fn(),
  })),
}));
} catch (error) {
  console.info("Just for info mocking leaflet: leaflet is not installed");
}

// ---- Editors ----

// Monaco
try {
jest.mock("monaco-editor", () => ({
  editor: {
    create: jest.fn(),
  },
}));
} catch (error) {
  console.info("Just for info mocking monaco-editor: monaco-editor is not installed");
}

// ---- Browser APIs often missing in Jest ----
// Plotly.js and @plotly/d3 expect `self` (browser global); Node has no `self`
if (typeof globalThis !== 'undefined') {
  global.self = globalThis;
} else {
  global.self = global;
}

try {
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

global.IntersectionObserver = class {
  observe() {}
  disconnect() {}
};
} catch (error) {
  console.info("Just for info mocking ResizeObserver: ResizeObserver is not installed");
}

try {
  global.IntersectionObserver = class {
    observe() {}
    disconnect() {}
  };
} catch (error) {
  console.info("Just for info mocking IntersectionObserver: IntersectionObserver is not installed");
}
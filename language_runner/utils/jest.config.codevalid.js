/**
 * Jest config for running all tests under .codevalid (CodeValid-generated tests).
 * Use from repo root: npx jest --config .codevalid/jest.config.js
 */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  rootDir: "..",
  roots: ["<rootDir>/.codevalid"],
  testMatch: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  transform: {
    "^.+\\.(ts|tsx)$": "ts-jest",
  },
  // allow imports from src or project root
  moduleDirectories: [
    "node_modules",
    "<rootDir>",
    "<rootDir>/src"
  ],
  moduleNameMapper: {
    // CSS modules
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    // images + fonts
    "\\.(png|jpg|jpeg|gif|svg|webp|avif|ico|bmp|ttf|woff|woff2|eot)$":
      "<rootDir>/.codevalid/mocks/fileMock.js",
    "^(\\.{1,2}/.*)\\.js$": "$1",
    "^highcharts/modules/.*$": "<rootDir>/.codevalid/mocks/highchartsModuleMock.js"
  },
  globals: {
    "ts-jest": {
      isolatedModules: true
    }
  },
  setupFilesAfterEnv: ["<rootDir>/.codevalid/jest.setup.js"],
  testPathIgnorePatterns: ["/node_modules/", "\\.d\\.ts$"],
  collectCoverageFrom: [".codevalid/**/*.{ts,tsx,js,jsx}", "!**/*.d.ts"],
  verbose: true,
};


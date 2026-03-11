/**
 * Jest config for running all tests under .codevalid (CodeValid-generated tests).
 * Use from repo root: npx jest --config .codevalid/jest.config.js
 */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  rootDir: "..",
  roots: ["<rootDir>/.codevalid"],
  testMatch: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  transform: {
    "^.+\\.(ts|tsx)$": "ts-jest",
  },
  moduleNameMapper: {
    "^(\\.{1,2}/.*)\\.js$": "$1",
  },
  testPathIgnorePatterns: ["/node_modules/", "\\.d\\.ts$"],
  collectCoverageFrom: [".codevalid/**/*.{ts,tsx,js,jsx}", "!**/*.d.ts"],
  verbose: true,
};

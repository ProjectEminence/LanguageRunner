"""
TypeScript/JavaScript test runner using Jest with coverage support.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_runner import BaseTestRunner


# Extensions that Jest typically runs (test files)
JEST_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")


class TypeScriptTestRunner(BaseTestRunner):
    """TypeScript/JavaScript test runner using Jest."""

    def _find_package_json(self, repo_path: str) -> Path | None:
        """Find package.json at repo root or in any subdirectory."""
        root = Path(repo_path)
        if (root / "package.json").exists():
            return root / "package.json"
        return next(root.rglob("package.json"), None)

    def detect_language(self, repo_path: str) -> bool:
        """Check if this is a Node/TypeScript project (has package.json)."""
        return self._find_package_json(repo_path) is not None

    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup Node environment: npm install from package.json.

        Args:
            repo_path: Path to the repository root

        Returns:
            Dictionary with setup results
        """
        try:
            package_json = self._find_package_json(repo_path)
            if not package_json:
                return {
                    "success": False,
                    "error": "No package.json found",
                    "output": "",
                }

            install_dir = str(package_json.parent)
            result = subprocess.run(
                ["npm", "install", "--legacy-peer-deps"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to run npm install: {result.stderr}",
                    "output": result.stdout,
                }
            # Ensure Jest is available (may be in devDependencies from package.json)
            jest_check = subprocess.run(
                ["npx", "jest", "--version"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if jest_check.returncode != 0:
                return {
                    "success": False,
                    "error": (
                        "Jest not found. Add jest to devDependencies in package.json, "
                        f"or install with: npm install -D jest. {jest_check.stderr}"
                    ),
                    "output": jest_check.stdout,
                }
            # run npm install --save-dev ts-jest @types/jest
            ts_jest_result = subprocess.run(
                ["npm", "install", "--save-dev", "ts-jest", "@types/jest", "--legacy-peer-deps"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if ts_jest_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to install ts-jest: {ts_jest_result.stderr}",
                    "output": ts_jest_result.stdout,
                }

            # Ensure .codevalid Jest config exists (for running tests under .codevalid)
            repo_root = Path(repo_path)
            codevalid_dir = repo_root / ".codevalid"
            codevalid_dir.mkdir(parents=True, exist_ok=True)

            jest_config_names = ("jest.config.js", "jest.config.ts", "jest.config.cjs")
            existing_config = next(
                (codevalid_dir / name for name in jest_config_names if (codevalid_dir / name).exists()),
                None,
            )
            files_to_commit: List[Dict[str, str]] = []

            if existing_config is None:
                sample_path = Path(__file__).parent / "utils" / "jest.config.codevalid.js"
                target_config = codevalid_dir / "jest.config.js"
                if sample_path.exists():
                    config_content = sample_path.read_text()
                    target_config.write_text(config_content)
                    files_to_commit.append(".codevalid/jest.config.js")
                else:
                    raise Exception("Jest config sample not found")

            result_payload: Dict[str, Any] = {
                "success": True,
                "output": "Environment setup completed successfully",
            }
            if files_to_commit:
                result_payload["files_to_commit"] = files_to_commit
            return result_payload

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Setup timed out",
                "output": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Setup failed: {str(e)}",
                "output": "",
            }

    def run_tests(
        self,
        repo_path: str,
        test_files: List[str],
        include_coverage: bool = False
    ) -> Dict[str, Any]:
        """
        Run Jest on the given test files.

        Only runs TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx).
        Non-matching paths are ignored.

        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            include_coverage: Whether to collect and return coverage data (default: False)

        Returns:
            Dictionary with test results. If include_coverage=True, also includes coverage data.
        """
        try:
            ts_test_files = [
                f
                for f in test_files
                if f.lower().endswith(JEST_EXTENSIONS)
            ]
            if not ts_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": [
                        "No TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx) to run. "
                        "Received paths may be for another language (e.g. .py)."
                    ],
                }

            repo = Path(repo_path)
            absolute_test_files = [str(repo / f) for f in ts_test_files]
            existing_test_files = [f for f in absolute_test_files if Path(f).exists()]

            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No test files found"],
                }

            package_json = self._find_package_json(repo_path)
            cwd = str(package_json.parent) if package_json else repo_path

            # Use .codevalid Jest config when present (for tests under .codevalid)
            codevalid_config = Path(repo_path) / ".codevalid" / "jest.config.js"
            use_codevalid_config = codevalid_config.exists()

            # Run Jest with JSON output to a temp file for reliable parsing
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as tmp:
                output_file = tmp.name

            try:
                cmd = [
                    "npx",
                    "--yes",
                    "jest",
                    "--json",
                    f"--outputFile={output_file}",
                    "--no-cache",
                    "--runTestsByPath",
                    *existing_test_files,
                ]
                
                # Add coverage flags if requested
                if include_coverage:
                    cmd.extend(["--coverage", "--coverageReporters=json"])
                
                if use_codevalid_config:
                    cmd.extend(["--config", str(codevalid_config.resolve())])
                else:
                    cmd.extend(["--preset=ts-jest"])

                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    input="y\n",
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 minutes
                )

                test_results = []
                coverage = None
                errors: List[str] = []

                # Parse Jest JSON output (includes coverage data when --coverage is used)
                if Path(output_file).exists():
                    try:
                        with open(output_file, "r") as f:
                            jest_output = json.load(f)
                        test_results = self._parse_jest_results(
                            jest_output, repo_path, existing_test_files
                        )
                        # Extract coverage from Jest output if requested
                        if include_coverage:
                            coverage = self._parse_jest_coverage(jest_output, repo_path)
                        
                        if result.returncode != 0 and not any(
                            r["status"] == "failed" for r in test_results
                        ):
                            errors = [result.stderr] if result.stderr else []
                    except (json.JSONDecodeError, KeyError) as e:
                        errors.append(f"Failed to parse Jest output: {e}")

                # Fallback if no JSON or parsing failed
                if not test_results:
                    for test_file in existing_test_files:
                        rel_path = str(Path(test_file).relative_to(repo_path))
                        test_results.append({
                            "test_file": rel_path,
                            "test_name": rel_path,
                            "status": "passed" if result.returncode == 0 else "failed",
                            "error": result.stderr if result.returncode != 0 else None,
                            "output": result.stdout,
                        })

                return {
                    "success": result.returncode == 0,
                    "test_results": test_results,
                    "coverage": coverage,
                    "errors": errors
                    if errors
                    else ([] if result.returncode == 0 else [result.stderr or ""]),
                }
            finally:
                Path(output_file).unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"],
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests: {str(e)}"],
            }

    def _parse_jest_results(
        self,
        jest_output: Dict[str, Any],
        repo_path: str,
        existing_test_files: List[str],
    ) -> List[Dict[str, Any]]:
        """Convert Jest JSON output to the same structure as Python runner."""
        test_results: List[Dict[str, Any]] = []
        repo = Path(repo_path)

        for file_result in jest_output.get("testResults", []):
            file_name = file_result.get("name", "")
            try:
                rel_file = str(Path(file_name).relative_to(repo))
            except ValueError:
                rel_file = file_name

            for assertion in file_result.get("assertionResults", []):
                title = assertion.get("title", "")
                full_name = assertion.get("fullName", title)
                status = assertion.get("status", "failed")
                failure_messages = assertion.get("failureMessages", [])
                error_text = "\n".join(failure_messages) if failure_messages else None

                test_results.append({
                    "test_file": rel_file,
                    "test_name": f"{rel_file}::{full_name}",
                    "status": "passed" if status == "passed" else "failed",
                    "error": error_text,
                    "output": "",
                })

        return test_results

    def _parse_jest_coverage(
        self,
        jest_output: Dict[str, Any],
        repo_path: str
    ) -> Optional[Dict[str, Any]]:
        """Parse Jest coverage data from JSON output into standardized format."""
        coverage_map = jest_output.get("coverageMap", {})
        if not coverage_map:
            # Try alternative key names
            coverage_map = jest_output.get("coverage", {})
        
        if not coverage_map:
            return None
        
        files_covered = []
        total_lines = 0
        total_covered = 0
        
        for file_path, file_data in coverage_map.items():
            stmt = file_data.get("s", {})  # statements
            covered_statements = sum(1 for v in stmt.values() if v > 0)
            total_statements = len(stmt)
            
            if total_statements > 0:
                pct = (covered_statements / total_statements) * 100
                files_covered.append({
                    'file': file_path,
                    'line_coverage': round(pct, 2),
                    'lines_covered': covered_statements,
                    'lines_total': total_statements,
                })
                total_lines += total_statements
                total_covered += covered_statements
        
        line_coverage = (total_covered / total_lines * 100) if total_lines > 0 else 0
        
        return {
            'line_coverage': round(line_coverage, 2),
            'lines_covered': total_covered,
            'lines_total': total_lines,
            'files_covered': len(files_covered),
            'coverage_by_file': files_covered,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

    def run_tests_with_coverage(
        self,
        repo_path: str,
        test_files: List[str],
        coverage_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run Jest with coverage on the given test files.

        Only runs TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx).
        Non-matching paths are ignored.

        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            coverage_options: Optional dict with keys:
                - collect_coverage_from: list of paths to collect coverage from
                - coverage_threshold: minimum coverage percentage required

        Returns:
            Dictionary with test results and coverage data
        """
        coverage_options = coverage_options or {}
        
        try:
            ts_test_files = [
                f
                for f in test_files
                if f.lower().endswith(JEST_EXTENSIONS)
            ]
            if not ts_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": [
                        "No TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx) to run. "
                        "Received paths may be for another language (e.g. .py)."
                    ],
                }

            repo = Path(repo_path)
            absolute_test_files = [str(repo / f) for f in ts_test_files]
            existing_test_files = [f for f in absolute_test_files if Path(f).exists()]

            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No test files found"],
                }

            package_json = self._find_package_json(repo_path)
            cwd = str(package_json.parent) if package_json else repo_path

            # Use .codevalid Jest config when present (for tests under .codevalid)
            codevalid_config = Path(repo_path) / ".codevalid" / "jest.config.js"
            use_codevalid_config = codevalid_config.exists()

            # Run Jest with JSON output and coverage
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as tmp:
                output_file = tmp.name

            try:
                cmd = [
                    "npx",
                    "--yes",
                    "jest",
                    "--json",
                    f"--outputFile={output_file}",
                    "--no-cache",
                    "--coverage",
                    "--coverageReporters=json",
                    "--runTestsByPath",
                    *existing_test_files,
                ]
                
                # Add coverage options if provided
                collect_from = coverage_options.get('collect_coverage_from')
                if collect_from:
                    cmd.extend([f"--coveragePathIgnorePatterns=/node_modules/"])
                
                if use_codevalid_config:
                    cmd.extend(["--config", str(codevalid_config.resolve())])
                else:
                    cmd.extend(["--preset=ts-jest"])

                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    input="y\n",
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 minutes
                )

                test_results = []
                coverage = None
                errors: List[str] = []

                # Parse Jest JSON output (includes coverage data)
                if Path(output_file).exists():
                    try:
                        with open(output_file, "r") as f:
                            jest_output = json.load(f)
                        test_results = self._parse_jest_results(
                            jest_output, repo_path, existing_test_files
                        )
                        # Extract coverage from Jest output
                        coverage = self._parse_jest_coverage(jest_output, repo_path)
                        
                        if result.returncode != 0 and not any(
                            r["status"] == "failed" for r in test_results
                        ):
                            errors = [result.stderr] if result.stderr else []
                    except (json.JSONDecodeError, KeyError) as e:
                        errors.append(f"Failed to parse Jest output: {e}")

                # Fallback if no JSON or parsing failed
                if not test_results:
                    for test_file in existing_test_files:
                        rel_path = str(Path(test_file).relative_to(repo_path))
                        test_results.append({
                            "test_file": rel_path,
                            "test_name": rel_path,
                            "status": "passed" if result.returncode == 0 else "failed",
                            "error": result.stderr if result.returncode != 0 else None,
                            "output": result.stdout,
                        })

                return {
                    "success": result.returncode == 0,
                    "test_results": test_results,
                    "coverage": coverage,
                    "errors": errors
                    if errors
                    else ([] if result.returncode == 0 else [result.stderr or ""]),
                }
            finally:
                Path(output_file).unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"],
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests with coverage: {str(e)}"],
            }

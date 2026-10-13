const dryRun = (process.env.RELEASE_DRY_RUN || "false").toLowerCase() === "true";
const testPypi = (process.env.RELEASE_TEST_PYPI || "false").toLowerCase() === "true";
const pypiToken = process.env.PYPI_TOKEN;
const testPypiToken = process.env.TEST_PYPI_TOKEN;

const prepareCmd = "uv version ${nextRelease.version} && uv build";
let publishCmd = "uv publish --token ";

if (testPypi) {
  publishCmd += `${testPypiToken} --index testpypi`;
} else {
  publishCmd += `${pypiToken}`;
}

if (dryRun) {
  publishCmd += " --dry-run";
}

import config from "semantic-release-preconfigured-conventional-commits" with { type: "json" };

config.plugins.push([
  "@semantic-release/exec",
  {
    prepareCmd,
    publishCmd,
  },
]);

if (!dryRun) {
  config.plugins.push(
    [
      "@semantic-release/github",
      {
        assets: [{ path: "dist/*" }],
      },
    ],
    [
      "@semantic-release/git",
      {
        assets: ["CHANGELOG.md", "pyproject.toml", "uv.lock"],
        message: "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
      },
    ],
  );
}

export default config;

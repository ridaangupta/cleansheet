// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');

const crypto = require('crypto');
const path = require('path');
const fs = require('fs');

function hashFileContent(filePath, hashName = 'sha256') {
  if (!fs.existsSync(filePath)) {
    return;
  } else {
    const hash = crypto.createHash(hashName);
    hash.update(fs.readFileSync(filePath));
    return hash.digest('hex');
  }
}

const cacheVersion = hashFileContent('.env');

/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('@react-native/metro-config').MetroConfig}
 */
// ../shared holds the Cleansheet sidecar contract (shared/sidecar), reused from the browser harness.
const config = {
  cacheVersion,
  watchFolders: [path.resolve(__dirname, '../shared')],
  // Files under ../shared would otherwise resolve dependencies (e.g. @babel/runtime helpers)
  // from the repo root, which doesn't have the app's packages.
  resolver: {
    nodeModulesPaths: [path.resolve(__dirname, 'node_modules')],
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);

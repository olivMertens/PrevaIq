const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { load, srcDir } = require('./loadTs');

const claimMap = load('claimMap.ts', path.join(srcDir, 'lib'));
const root = path.resolve(__dirname, '..', '..');
const scenarios = [
  ['habitation-ch', 'swiss-chocolate-storm', 'Steinberggasse 23', '8400 Winterthur', 9],
  ['habitation-ch-watch', 'swiss-watch-storm', 'Mühlentalstrasse 185', '8200 Schaffhausen', 14],
];

test('document preview and download actions have localized accessible labels', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(
      path.join(root, 'frontend', 'messages', `${locale}.json`), 'utf8',
    ));
    for (const key of ['view', 'download', 'openNewTab']) {
      assert.equal(typeof messages.documents[key], 'string', `${locale}: documents.${key}`);
      assert.ok(messages.documents[key].trim().length > 0);
    }
  }
});

test('Swiss guides disclose real map anchors and use existing, non-duplicated upload sets', () => {
  for (const [id, folder, street, town, count] of scenarios) {
    const directory = path.join(root, 'assets', 'demo-prevaiq', 'property-claims', folder);
    const files = fs.readdirSync(directory).filter(name => /\.(pdf|jpg)$/.test(name));
    assert.equal(files.length, count);
    assert.ok(files.includes('schadenmeldung-geschaeftsversicherung.pdf'));
    for (const locale of ['en', 'fr', 'de']) {
      const messages = JSON.parse(fs.readFileSync(path.join(root, 'frontend', 'messages', `${locale}.json`), 'utf8'));
      const scenario = messages.demoGuide.scenarios[id];
      assert.ok(scenario.steps[0].tip.includes(street));
      assert.ok(scenario.steps[0].tip.includes(town));
      assert.match(scenario.steps[0].tip, /Street View/);
      assert.ok(scenario.steps[1].detail.includes(String(count)));
      assert.match(scenario.steps[1].detail, /\.eml/);
      assert.match(scenario.steps[1].tip, new RegExp(folder));
      assert.ok(scenario.steps[2].detail.includes(messages.claims.evidence.cgSwissBusiness));
      assert.match(scenario.steps[2].detail, /CHF/);
    }
  }
});

test('both verified Swiss demo anchors enable precise map, Street View and directions links', () => {
  for (const [, folder, street, town] of scenarios) {
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'assets', 'demo-prevaiq', 'property-claims', folder, 'manifest.json'), 'utf8'));
    const anchor = manifest.map_anchor;
    assert.equal(anchor.address, `${street}, ${town}, Schweiz`);
    const place = { ...anchor.verified_result, precise: anchor.verified_result.level === 'building' };
    assert.equal(place.precise, true);
    const coordinates = `${place.lat.toFixed(6)},${place.lon.toFixed(6)}`;
    assert.ok(claimMap.googleMapsUrl(anchor.address, place).endsWith(`query=${coordinates}`));
    assert.ok(claimMap.streetViewUrl(place).endsWith(`viewpoint=${coordinates}`));
    assert.ok(claimMap.directionsUrl(anchor.address, place).endsWith(`destination=${coordinates}`));
    for (const basemap of ['plan', 'satellite']) {
      assert.ok(claimMap.tilesAround(place.lat, place.lon, 17, basemap).length > 0);
    }
  }
});

test('Swiss property evidence references only Swiss AVB, without French or health policies', () => {
  const { propertyPolicyReferences } = load(
    'propertyClaimHelpers.ts',
    path.join(srcDir, 'components', 'claims', 'property'),
  );
  const refs = propertyPolicyReferences('CH');
  assert.deepEqual(refs.map(ref => ref.id), ['kmu_ch']);
  assert.deepEqual(propertyPolicyReferences('FR').map(ref => ref.id), ['habitation', 'sante']);
  assert.deepEqual(propertyPolicyReferences().map(ref => ref.id), ['habitation', 'sante']);
  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(
      path.join(root, 'frontend', 'messages', `${locale}.json`), 'utf8',
    ));
    for (const ref of refs) {
      assert.equal(typeof messages.claims.evidence[ref.labelKey], 'string');
      assert.equal(typeof messages.claims.evidence[ref.descriptionKey], 'string');
    }
    assert.equal(typeof messages.claims.evidence.policy, 'string');
  }
});

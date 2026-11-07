const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { load, srcDir } = require('./loadTs');

const claimMap = load('claimMap.ts', path.join(srcDir, 'lib'));

test('the map is built from the tiles around the loss, with the loss at its centre', () => {
  const { worldPixel, tilesAround } = claimMap;
  assert.deepEqual(worldPixel(0, 0, 0), { x: 128, y: 128 });
  assert.deepEqual(worldPixel(0, 0, 1), { x: 256, y: 256 });

  // 5 Place Bellecour, Lyon, at building level.
  const lat = 45.7578;
  const lon = 4.832;
  const tiles = tilesAround(lat, lon, 17, 'satellite', 640, 320);
  const center = worldPixel(lat, lon, 17);
  const [z, x, y] = [17, Math.floor(center.x / 256), Math.floor(center.y / 256)];
  const middle = tiles.find((tile) => tile.key === `${z}/${x}/${y}`);
  assert.ok(middle, 'the tile holding the loss is shown');
  // Its position in the view puts the loss exactly at the centre (50 %, 50 %).
  assert.ok(Math.abs(middle.left + ((center.x - x * 256) / 640) * 100 - 50) < 1e-9);
  assert.ok(Math.abs(middle.top + ((center.y - y * 256) / 320) * 100 - 50) < 1e-9);
  assert.equal(middle.url, `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/17/${y}/${x}`);
  // The tiles cover the whole view.
  assert.ok(Math.min(...tiles.map((tile) => tile.left)) <= 0);
  assert.ok(Math.max(...tiles.map((tile) => tile.left + tile.width)) >= 100);
  assert.ok(Math.min(...tiles.map((tile) => tile.top)) <= 0);
  assert.ok(Math.max(...tiles.map((tile) => tile.top + tile.height)) >= 100);

  const plan = tilesAround(lat, lon, 17, 'plan', 640, 320).find((tile) => tile.key === middle.key);
  assert.equal(plan.url, `https://tile.openstreetmap.org/17/${x}/${y}.png`);
  assert.equal(claimMap.basemapAttribution('plan'), '© OpenStreetMap contributors');
});

test('map links point at the building only when its street number was found', () => {
  const { googleMapsUrl, streetViewUrl, directionsUrl } = claimMap;
  const precise = { lat: 45.7578, lon: 4.832, precise: true };
  const town = { lat: 47.4988, lon: 8.7241, precise: false };

  assert.equal(googleMapsUrl('5 Place Bellecour, 69002 Lyon', precise), 'https://www.google.com/maps/search/?api=1&query=45.757800,4.832000');
  assert.equal(
    googleMapsUrl('Kakaogasse 7, 8400 Winterthur', town),
    'https://www.google.com/maps/search/?api=1&query=Kakaogasse%207%2C%208400%20Winterthur',
  );
  assert.equal(googleMapsUrl('Kakaogasse 7, 8400 Winterthur', null), googleMapsUrl('Kakaogasse 7, 8400 Winterthur', town));
  assert.equal(streetViewUrl(precise), 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=45.757800,4.832000');
  assert.equal(directionsUrl('5 Place Bellecour, 69002 Lyon', precise), 'https://www.google.com/maps/dir/?api=1&destination=45.757800,4.832000');
  assert.equal(
    directionsUrl('Kakaogasse 7, 8400 Winterthur', town),
    'https://www.google.com/maps/dir/?api=1&destination=Kakaogasse%207%2C%208400%20Winterthur',
  );
});

test('every location card label exists in English, French and German', () => {
  const keys = [
    'title', 'loading', 'basemap', 'satellite', 'plan', 'openMap', 'insured', 'approximateStreet', 'approximateTown',
    'notFound', 'unavailable', 'noAddress', 'googleMaps', 'streetView', 'directions', 'geocoding',
  ];
  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'messages', `${locale}.json`), 'utf8'));
    const labels = messages.caseCockpit.location;
    assert.deepEqual(keys.filter((key) => typeof labels?.[key] !== 'string'), [], `${locale} caseCockpit.location`);
    assert.match(labels.approximateStreet, /\{place\}/);
    assert.match(labels.approximateTown, /\{place\}/);
  }
  const cockpit = fs.readFileSync(path.join(srcDir, 'components', 'claims', 'PropertyCasualtyClaimsOverview.tsx'), 'utf8');
  assert.match(cockpit, /<WeatherEvidencePanel applicationId=\{application\.id\} claimDate=\{claimDate\}/);
});

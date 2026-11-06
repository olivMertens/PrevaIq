// Where the loss happened, on a small map built from map tiles (no map library), and the
// links that open it in Google Maps. Pure module (no imports) so tests can load it.

export type Basemap = 'satellite' | 'plan';
export const BASEMAPS: readonly Basemap[] = ['satellite', 'plan'];

// Same free sources as PrevaIQ FDR: Esri World Imagery and OpenStreetMap, with their credits.
const SOURCES: Record<Basemap, { url: (z: number, x: number, y: number) => string; attribution: string }> = {
  satellite: {
    url: (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`,
    attribution: '© Esri, Maxar, Earthstar Geographics',
  },
  plan: {
    url: (z, x, y) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`,
    attribution: '© OpenStreetMap contributors',
  },
};

const TILE = 256;

export function basemapAttribution(basemap: Basemap): string {
  return SOURCES[basemap].attribution;
}

/** Position in pixels of the Web Mercator world map at a zoom level (256 px tiles). */
export function worldPixel(lat: number, lon: number, zoom: number): { x: number; y: number } {
  const size = TILE * 2 ** zoom;
  const sin = Math.min(Math.max(Math.sin((lat * Math.PI) / 180), -0.9999), 0.9999);
  return {
    x: ((lon + 180) / 360) * size,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size,
  };
}

export interface MapTile {
  key: string;
  url: string;
  /** Position and size in percent of the view, so the map scales with its container. */
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Tiles covering a view of width × height pixels centred on a position. */
export function tilesAround(lat: number, lon: number, zoom: number, basemap: Basemap, width = 640, height = 320): MapTile[] {
  const center = worldPixel(lat, lon, zoom);
  const originX = center.x - width / 2;
  const originY = center.y - height / 2;
  const count = 2 ** zoom;
  const tiles: MapTile[] = [];
  for (let y = Math.floor(originY / TILE); y <= Math.floor((originY + height - 1) / TILE); y += 1) {
    if (y < 0 || y >= count) continue;
    for (let x = Math.floor(originX / TILE); x <= Math.floor((originX + width - 1) / TILE); x += 1) {
      tiles.push({
        key: `${zoom}/${x}/${y}`,
        url: SOURCES[basemap].url(zoom, ((x % count) + count) % count, y),
        left: ((x * TILE - originX) / width) * 100,
        top: ((y * TILE - originY) / height) * 100,
        width: (TILE / width) * 100,
        height: (TILE / height) * 100,
      });
    }
  }
  return tiles;
}

export interface MapPlace {
  lat: number;
  lon: number;
  /** The street number was found; otherwise the position is the street or the town. */
  precise: boolean;
}

const coordinates = (place: MapPlace) => `${place.lat.toFixed(6)},${place.lon.toFixed(6)}`;

/**
 * Google Maps on the exact point when the street number was found; otherwise a search on the
 * address, so the link never points at a town centre presented as the building.
 */
export function googleMapsUrl(address: string, place?: MapPlace | null): string {
  const query = place?.precise ? coordinates(place) : encodeURIComponent(address);
  return `https://www.google.com/maps/search/?api=1&query=${query}`;
}

/** Street View at the building (only meaningful for a precise position). */
export function streetViewUrl(place: MapPlace): string {
  return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${coordinates(place)}`;
}

/** Route to the loss location, e.g. for the loss adjuster's visit. */
export function directionsUrl(address: string, place?: MapPlace | null): string {
  const destination = place?.precise ? coordinates(place) : encodeURIComponent(address);
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}`;
}

'use client';

import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { Car, ExternalLink, MapPin, PersonStanding, TriangleAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getClaimLocation, type ClaimLocation, type PlaceLevel } from '@/lib/api';
import {
  BASEMAPS,
  basemapAttribution,
  directionsUrl,
  googleMapsUrl,
  streetViewUrl,
  tilesAround,
  type Basemap,
} from '@/lib/claimMap';
import { CockpitCard } from './caseUi';
import { usePersistentChoice } from './usePersistentState';
import AuroraRiskPanel from './AuroraRiskPanel';

// Zoom on what was found: the building, its street or its town.
const ZOOM: Record<PlaceLevel, number> = { building: 17, street: 16, town: 13 };
const LINK = 'inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50';

/** Where the loss happened: a map of the address, and links to Google Maps, Street View and a route. */
export default function LocationCard({
  applicationId,
  claimDate,
}: {
  applicationId: string;
  claimDate?: string;
}) {
  const t = useTranslations('caseCockpit.location');
  const [location, setLocation] = useState<ClaimLocation | null>(null);
  const [failed, setFailed] = useState(false);
  const [basemap, setBasemap] = usePersistentChoice<Basemap>('prevaiq.map.basemap', 'satellite', BASEMAPS);

  useEffect(() => {
    let active = true;
    getClaimLocation(applicationId).then(
      (value) => {
        if (active) setLocation(value);
      },
      () => {
        if (active) setFailed(true);
      },
    );
    return () => {
      active = false;
    };
  }, [applicationId]);

  const place = location?.place ?? null;
  const address = location?.address ?? null;
  const searchAddress = location?.search_address ?? address ?? '';

  const basemapSwitch = place ? (
    <div role="radiogroup" aria-label={t('basemap')} className="flex rounded-lg bg-slate-100 p-0.5 text-xs font-medium">
      {BASEMAPS.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={basemap === option}
          onClick={() => setBasemap(option)}
          className={clsx('rounded-md px-2 py-1 transition-colors', basemap === option ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700')}
        >
          {t(option)}
        </button>
      ))}
    </div>
  ) : undefined;

  let body: React.ReactNode;
  if (!location && !failed) {
    body = <div className="aspect-[2/1] animate-pulse rounded-lg bg-slate-100" role="status" aria-label={t('loading')} />;
  } else if (failed || location?.status === 'no_address' || !address) {
    body = <p className="text-sm text-slate-500">{failed ? t('unavailable') : t('noAddress')}</p>;
  } else {
    body = (
      <div className="space-y-3">
        {place && (
          <a
            href={googleMapsUrl(searchAddress, place)}
            target="_blank"
            rel="noopener noreferrer"
            title={t('openMap')}
            aria-label={t('openMap')}
            className="relative block aspect-[2/1] overflow-hidden rounded-lg bg-slate-200 ring-1 ring-slate-200"
          >
            {tilesAround(place.lat, place.lon, ZOOM[place.level], basemap).map((tile) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={`${basemap}/${tile.key}`}
                src={tile.url}
                alt=""
                loading="lazy"
                decoding="async"
                draggable={false}
                className="absolute max-w-none select-none"
                style={{ left: `${tile.left}%`, top: `${tile.top}%`, width: `${tile.width}%`, height: `${tile.height}%` }}
              />
            ))}
            {place.level === 'building' ? (
              <MapPin
                className="absolute left-1/2 top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-full fill-rose-600 text-white drop-shadow"
                strokeWidth={1.5}
                aria-hidden
              />
            ) : (
              <span
                className={clsx(
                  'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-dashed border-amber-400 bg-amber-300/20',
                  place.level === 'street' ? 'h-16 w-16' : 'h-24 w-24',
                )}
                aria-hidden
              />
            )}
            <span className="absolute bottom-0 right-0 rounded-tl bg-white/80 px-1.5 py-0.5 text-[10px] text-slate-600">
              {basemapAttribution(basemap)}
            </span>
          </a>
        )}

        <div className="flex gap-2 text-sm">
          <MapPin className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400" aria-hidden />
          <div className="min-w-0">
            <p className="font-medium text-slate-900">{address}</p>
            {location?.kind === 'insured' && <p className="text-xs text-slate-500">{t('insured')}</p>}
            {location?.status === 'resolved' && place && place.level !== 'building' && (
              <p className="mt-0.5 flex gap-1 text-xs text-amber-800">
                <TriangleAlert className="mt-px h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                {t(place.level === 'street' ? 'approximateStreet' : 'approximateTown', { place: place.label })}
              </p>
            )}
            {location?.status === 'not_found' && <p className="mt-0.5 text-xs text-amber-800">{t('notFound')}</p>}
            {location?.status === 'unavailable' && <p className="mt-0.5 text-xs text-amber-800">{t('unavailable')}</p>}
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <a href={googleMapsUrl(searchAddress, place)} target="_blank" rel="noopener noreferrer" className={LINK}>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            {t('googleMaps')}
          </a>
          {place?.level === 'building' && (
            <a href={streetViewUrl(place)} target="_blank" rel="noopener noreferrer" className={LINK}>
              <PersonStanding className="h-3.5 w-3.5" aria-hidden />
              {t('streetView')}
            </a>
          )}
          <a href={directionsUrl(searchAddress, place)} target="_blank" rel="noopener noreferrer" className={LINK}>
            <Car className="h-3.5 w-3.5" aria-hidden />
            {t('directions')}
          </a>
        </div>

        {place && <p className="text-[11px] text-slate-400">{t('geocoding')}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <CockpitCard title={t('title')} headingId="cockpit-location" aside={basemapSwitch}>
        <div className="px-4 py-3">{body}</div>
      </CockpitCard>
      <AuroraRiskPanel
          applicationId={applicationId}
          latitude={place?.lat}
          longitude={place?.lon}
          claimDate={claimDate}
      />
    </div>
  );
}

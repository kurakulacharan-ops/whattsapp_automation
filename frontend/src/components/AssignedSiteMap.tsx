import { useState } from 'react';
import axios from 'axios';
import { apiClient } from '../api/client';

export interface SiteValue {
  name: string;
  lat: number;
  long: number;
  place?: string | null;
  city?: string | null;
  district?: string | null;
  match_level?: 'city' | 'district';
  district_id?: string | null;
  dataset_id?: string | null;
  status?: string;
}

export function AssignedSiteMap({ site, onChange }: { site?: SiteValue; onChange: (site: SiteValue | undefined) => void }) {
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoMessage, setPhotoMessage] = useState('');
  async function uploadPhoto(file?: File) {
    if (!file) return;
    setPhotoBusy(true); setPhotoMessage('');
    try {
      const data = new FormData(); data.append('file', file);
      const response = await apiClient.post('/sites/extract-photo', data);
      const result = response.data as SiteValue;
      const place = result.place?.trim() || (
        result.name !== 'GPS photo location' ? result.name.trim() : null
      );
      onChange({
        name: place || result.name,
        lat: result.lat,
        long: result.long,
        city: result.city ?? null,
        district: result.district ?? null,
        district_id: result.district_id ?? null,
        dataset_id: result.dataset_id ?? null,
        match_level: 'city' as const,
      });
      setPhotoMessage(result.city || result.district
        ? 'City/town detected from GPS. Review before saving.'
        : 'GPS saved in the form. City lookup unavailable; range checks still work, but outside-range submissions may need manual review.');
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
      setPhotoMessage(typeof detail === 'string' ? detail : 'Could not extract GPS. Enter coordinates manually.');
    }
    finally { setPhotoBusy(false); }
  }
  const valid = site && Number.isFinite(site.lat) && Number.isFinite(site.long) && site.lat >= -90 && site.lat <= 90 && site.long >= -180 && site.long <= 180;
  async function resolveCoordinates(lat: number, long: number) {
    setPhotoBusy(true);
    setPhotoMessage('Looking up city/town...');
    const updated = { name: site?.name || 'Assigned site', lat, long, city: null, district: null, match_level: 'city' as const };
    onChange(updated);
    try {
      const { data } = await apiClient.post('/sites/resolve-location', { lat, long });
      onChange({ ...updated, name: data.place || updated.name, city: data.city ?? null, district: data.district ?? null, district_id: data.district_id ?? null, dataset_id: data.dataset_id ?? null });
      setPhotoMessage(data.city || data.district ? 'City/town detected. Review before saving.' : 'City/town lookup unavailable. Range checks still work; outside-range submissions may need manual review.');
    } catch {
      setPhotoMessage('City lookup unavailable. Please retry.');
    } finally {
      setPhotoBusy(false);
    }
  }

  function locate() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (position) => void resolveCoordinates(position.coords.latitude, position.coords.longitude),
      () => setPhotoMessage('Could not access your location. Allow location access or upload a GPS photo.'),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  return (
    <div className="col-span-2 rounded-md border p-3" style={{ borderColor: 'var(--color-border)' }}>
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-xs font-medium" style={{ color: 'var(--color-ink)' }}>Assigned location</div>
          <div className="text-[11px]" style={{ color: 'var(--color-ink-faint)' }}>Within the allowed range: pass. Outside that range: check the same city/town. Default range is 8 km.</div>
        </div>
        <button type="button" disabled={photoBusy} onClick={locate} className="px-2 py-1 rounded border text-xs" style={{ borderColor: 'var(--color-border)' }}>
          Use my location
        </button>
      </div>
      <label className="block text-xs mb-2">Optional: upload GPS Map Camera photo
        <input type="file" accept="image/jpeg,image/png,image/webp" disabled={photoBusy} onChange={e => void uploadPhoto(e.target.files?.[0])} className="block w-full mt-1" />
      </label>
      {photoMessage && <p className="text-xs mb-2" role="status">{photoMessage}</p>}
      <fieldset disabled={photoBusy} className="grid grid-cols-3 gap-2 mb-2">
        <input value={site?.name ?? ''} onChange={(e) => onChange({ ...site, name: e.target.value, lat: site?.lat ?? 0, long: site?.long ?? 0 })} placeholder="Location name" className="px-2 py-1.5 rounded border text-sm col-span-3" />
        <input type="number" step="any" value={site?.lat ?? ''} onChange={(e) => onChange({ ...site, name: site?.name ?? '', lat: Number(e.target.value), long: site?.long ?? 0, city: null, district: null, district_id: null, dataset_id: null })} placeholder="Latitude" className="px-2 py-1.5 rounded border text-sm" />
        <input type="number" step="any" value={site?.long ?? ''} onChange={(e) => onChange({ ...site, name: site?.name ?? '', lat: site?.lat ?? 0, long: Number(e.target.value), city: null, district: null, district_id: null, dataset_id: null })} placeholder="Longitude" className="px-2 py-1.5 rounded border text-sm" />
        <button type="button" onClick={() => onChange(undefined)} className="px-2 py-1.5 rounded border text-sm" style={{ borderColor: 'var(--color-border)' }}>Clear</button>
      </fieldset>
      <button type="button" disabled={!valid || photoBusy} onClick={() => site && void resolveCoordinates(site.lat, site.long)} className="px-2 py-1 rounded border text-xs">Detect city/town from coordinates</button>
      <div className="mt-2 text-sm">
        <label>City / town
          <input value={site?.city ?? ''} readOnly placeholder="Detect city/town from GPS" className="block w-full px-2 py-1.5 rounded border text-sm" />
        </label>
        <p className="text-xs mt-2">District: {site?.district || 'Not detected'}</p>
        <p className="text-xs mt-2">Outside the allowed range and registered city/town, or unable to verify: flagged for the manual team. District alone is not a match.</p>
      </div>
      <p className="text-[10px] mt-2" style={{ color: 'var(--color-ink-faint)' }}>
        City lookup sends coordinates only, not photos or employee details. Within-range attendance needs no city lookup.
        Location data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>.
      </p>

    </div>
  );
}

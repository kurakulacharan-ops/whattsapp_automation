import { useState, useRef, useEffect } from 'react';
import { UploadCloud, X } from 'lucide-react';
import { enrollFace } from '../api/employees';
import type { Employee } from '../types';

const MAX_PHOTOS = 5;

export function EnrollFaceModal({ employee, onClose }: { employee: Employee; onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Object URLs need explicit cleanup or they leak memory — regenerate
  // whenever the file list changes, revoke the previous batch on unmount/change.
  const [previews, setPreviews] = useState<string[]>([]);
  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);

  // Adds newly picked/dropped files to whatever's already selected, instead
  // of replacing the selection — picking files one at a time (rather than
  // multi-selecting in one dialog) previously wiped out earlier picks.
  // Dedupes by name+size+lastModified and caps at MAX_PHOTOS.
  function addFiles(incoming: FileList | File[]) {
    const incomingArr = Array.from(incoming).filter((f) => f.type.startsWith('image/'));
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`));
      const merged = [...prev];
      for (const f of incomingArr) {
        const key = `${f.name}-${f.size}-${f.lastModified}`;
        if (!seen.has(key) && merged.length < MAX_PHOTOS) {
          seen.add(key);
          merged.push(f);
        }
      }
      return merged;
    });
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await enrollFace(employee.employee_id, files);
      setResult(`Stored ${res.embeddings_stored} reference photo(s) for ${res.name}.`);
    } catch {
      setError('Enrollment failed — try again with clearer, front-facing photos.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        className="w-full max-w-md rounded-lg border p-6 shadow-xl"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-raised)' }}
      >
        <h2 className="text-base font-medium mb-1" style={{ color: 'var(--color-ink)' }}>
          Enroll face — {employee.name}
        </h2>
        <p className="text-sm mb-4" style={{ color: 'var(--color-ink-muted)' }}>
          5 reference selfies recommended for reliable matching; fewer will be accepted with a
          warning.
        </p>

        {result ? (
          <>
            <p className="text-sm mb-4" style={{ color: 'var(--color-present)' }}>
              {result}
            </p>
            <div className="flex justify-end">
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-md text-sm font-medium"
                style={{ background: 'var(--color-accent)', color: 'white' }}
              >
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = ''; // allow re-picking the same file after removal
              }}
              className="hidden"
            />

            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                addFiles(e.dataTransfer.files);
              }}
              disabled={files.length >= MAX_PHOTOS}
              className="w-full flex flex-col items-center justify-center gap-2 py-8 rounded-lg border-2 border-dashed text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                borderColor: dragActive ? 'var(--color-accent)' : 'var(--color-border)',
                background: dragActive ? 'var(--color-accent-bg)' : 'var(--color-surface-sunken)',
                color: 'var(--color-ink-muted)',
              }}
            >
              <UploadCloud size={24} style={{ color: 'var(--color-accent)' }} />
              <span>
                {files.length >= MAX_PHOTOS
                  ? 'Maximum photos selected'
                  : 'Drop photos here or click to browse'}
              </span>
              <span className="text-xs" style={{ color: 'var(--color-ink-faint)' }}>
                JPEG or PNG
              </span>
            </button>

            <p className="text-xs mt-2 mb-3" style={{ color: 'var(--color-ink-faint)' }}>
              {files.length} of {MAX_PHOTOS} selected
            </p>

            {files.length > 0 && (
              <div className="grid grid-cols-5 gap-2 mb-4">
                {previews.map((src, i) => (
                  <div key={i} className="relative aspect-square rounded-md overflow-hidden group">
                    <img src={src} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeFile(i)}
                      className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Remove"
                    >
                      <X size={16} color="white" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {error && (
              <p className="text-xs mb-3" style={{ color: 'var(--color-absent)' }}>
                {error}
              </p>
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={onClose} className="px-3 py-1.5 rounded-md text-sm" style={{ color: 'var(--color-ink-muted)' }}>
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={files.length === 0 || submitting}
                className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
                style={{ background: 'var(--color-accent)', color: 'white' }}
              >
                {submitting ? 'Uploading…' : 'Enroll'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
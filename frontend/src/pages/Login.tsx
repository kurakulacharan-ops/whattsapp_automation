import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate("/attendance");
    } catch (err) {
      if (axios.isAxiosError(err)) {
        if (!err.response) {
          setError(
            "Could not reach the backend. Is it running, and is the dev proxy target correct?",
          );
        } else if (err.response.status === 401 || err.response.status === 403) {
          setError("Username, password, or API key is incorrect.");
        } else {
          setError(
            `Login failed (${err.response.status}): ${JSON.stringify(err.response.data)}`,
          );
        }
      } else {
        setError("Something went wrong signing in.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="min-h-screen relative"
      style={{
        backgroundColor: "var(--color-surface)",
        backgroundImage: "url(/brand/login-bg.png)",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
      }}
    >
      {/* Positioned at the horizontal rule-of-thirds line (2/3 across),
          vertically centered — not dead-center on the page. */}
      <form
        onSubmit={handleSubmit}
        className="absolute w-full max-w-sm rounded-xl border p-8 shadow-lg"
        style={{
          top: "50%",
          left: "66.66%",
          transform: "translate(-50%, -50%)",
          borderColor: "var(--color-border)",
          background: "var(--color-surface-raised)",
        }}
      >
        <div className="flex justify-center mb-6">
          <img
            src="/brand/bigv-logo-tight.png"
            alt="bigV telecom"
            className="h-24 w-auto"
          />
        </div>

        <h1
          className="text-lg font-semibold text-center mb-1"
          style={{ color: "var(--color-ink)" }}
        >
          Attendance Admin
        </h1>
        <p
          className="text-sm text-center mb-6"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Sign in to review field attendance.
        </p>

        <label
          className="block text-xs mb-1"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Username
        </label>
        <input
          autoFocus
          required
          minLength={3}
          maxLength={50}
          pattern="[A-Za-z0-9_.-]+"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full mb-4 px-3 py-2 rounded-md text-sm border outline-none focus:ring-2"
          style={{
            background: "var(--color-surface-sunken)",
            borderColor: "var(--color-border)",
            color: "var(--color-ink)",
          }}
        />

        <label
          className="block text-xs mb-1"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Password
        </label>
        <div className="relative mb-4">
          <input
            type={showPassword ? "text" : "password"}
            required
            minLength={8}
            maxLength={72}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 pr-16 rounded-md text-sm border outline-none focus:ring-2"
            style={{
              background: "var(--color-surface-sunken)",
              borderColor: "var(--color-border)",
              color: "var(--color-ink)",
            }}
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>

        {error && (
          <p className="text-xs mb-4" style={{ color: "var(--color-absent)" }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50"
          style={{ background: "var(--color-accent)", color: "white" }}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <p
          className="text-center text-[11px] mt-6"
          style={{ color: "var(--color-ink-faint)" }}
        >
          Internal Operations Tool · WhatsApp Attendance Review Agent
        </p>
        <p
          className="text-center text-[11px] mt-1"
          style={{ color: "var(--color-ink-faint)" }}
        >
          © 2026 Big V Telecom
        </p>
      </form>
    </div>
  );
}

import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { Alert, Field, Spinner } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { errorMessage, fieldErrors } from '../lib/errors';
import { validateEmail, validatePassword } from '../lib/validation';

/** Registration form (UC-2 steps 2–5, RegisterPage in Section 8). */
export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Checked before any request is sent (RegisterPage.validateForm). */
  function validateForm() {
    const e: Record<string, string> = {};
    const emailErr = validateEmail(email);
    const pwErr = validatePassword(password);
    if (emailErr) e.email = emailErr;
    if (pwErr) e.password = pwErr;
    if (!confirm) e.confirm = 'Type your password again.';
    else if (confirm !== password) e.confirm = 'Passwords do not match.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function createAccount(ev: FormEvent) {
    ev.preventDefault();
    setFormError(null);
    if (!validateForm()) return;
    setBusy(true);
    try {
      await register(email.trim(), password);
      navigate('/setup', { replace: true });
    } catch (e) {
      setErrors(fieldErrors(e));
      setFormError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      step="Step 1 of 2"
      title="Create your account"
      subtitle="Then pick where you want your AI news."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-indigo-600 hover:underline">Log in</Link></>}
    >
      <form onSubmit={createAccount} className="space-y-4" noValidate>
        {formError && !Object.keys(errors).length && <Alert>{formError}</Alert>}
        <Field label="Email" htmlFor="email" error={errors.email}>
          {/* Cursor starts here (Change 3) */}
          <input id="email" type="email" autoComplete="email" autoFocus className={`input ${errors.email ? 'input-error' : ''}`} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password} hint="At least 8 characters.">
          <input id="password" type="password" autoComplete="new-password" className={`input ${errors.password ? 'input-error' : ''}`} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm" error={errors.confirm}>
          <input id="confirm" type="password" autoComplete="new-password" className={`input ${errors.confirm ? 'input-error' : ''}`} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy && <Spinner />} Create account
        </button>
      </form>
    </AuthLayout>
  );
}

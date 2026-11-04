import { cookies } from 'next/headers';
import LoginShell from '@/components/auth/LoginShell';

export default async function LoginLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const theme = cookieStore.get('login-theme')?.value === 'dark' ? 'dark' : 'light';
  return <LoginShell initialTheme={theme}>{children}</LoginShell>;
}

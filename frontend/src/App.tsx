import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ConfigProvider } from './context/ConfigContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/Login';
import { AttendancePage } from './pages/Attendance';
import { EmployeesPage } from './pages/Employees';
import { CoordinatorsPage } from './pages/Coordinators';
import { UserManagementPage } from './pages/UserManagement';
import { CoordinatorAttendancePage } from './pages/CoordinatorAttendance';
import { AttendanceCalendarPage } from './pages/AttendanceCalendar';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route element={<ProtectedRoute />}>
            <Route
              element={
                <ConfigProvider>
                  <Layout />
                </ConfigProvider>
              }
            >
              <Route path="/attendance" element={<AttendancePage />} />
              <Route path="/employees" element={<EmployeesPage />} />
              <Route element={<ProtectedRoute requireManualTeam />}>
                <Route path="/coordinators" element={<CoordinatorsPage />} />
                <Route path="/coordinator-attendance" element={<CoordinatorAttendancePage />} />
                <Route path="/attendance-calendar" element={<AttendanceCalendarPage />} />
                <Route path="/users" element={<UserManagementPage />} />
              </Route>
              <Route path="/" element={<Navigate to="/attendance" replace />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/attendance" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

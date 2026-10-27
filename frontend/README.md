# Attendance frontend

This is the consolidated `attendance_dev` React dashboard, using shared root
components plus the testing-stack attendance, participant, coordinator, and
export features. It calls the FastAPI backend through `/api`.

Use Node.js 22+ and run `npm ci`, `npm run build`, and `npm run lint`.
`npm run dev` serves port 5174 and proxies to the API on port 8001.
Production builds are served by the Nginx image through the deployment gateway.
See the root README and PRODUCTION_DEPLOYMENT.md for the complete workflow.

import { createBrowserRouter } from 'react-router-dom'

import Layout from './components/Layout'
import AuditPage from './pages/AuditPage'
import EntitiesPage from './pages/EntitiesPage'
import EntityPage from './pages/EntityPage'
import FindingPage from './pages/FindingPage'
import MethodologyPage from './pages/MethodologyPage'
import NegativeSpacePage from './pages/NegativeSpacePage'
import Overview from './pages/Overview'
import UploadPage from './pages/UploadPage'
import ValidationPage from './pages/ValidationPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: 'entities', element: <EntitiesPage /> },
      { path: 'entities/:entityId', element: <EntityPage /> },
      { path: 'findings/:findingId', element: <FindingPage /> },
      { path: 'negative-space', element: <NegativeSpacePage /> },
      { path: 'upload', element: <UploadPage /> },
      { path: 'validation', element: <ValidationPage /> },
      { path: 'methodology', element: <MethodologyPage /> },
      { path: 'audit', element: <AuditPage /> },
      {
        path: '*',
        element: (
          <div className="card card-pad">
            <p className="text-sm font-semibold">Page not found</p>
            <p className="mt-1 text-sm text-ink-500">
              That route does not exist. Use the sidebar to get back to the portfolio overview.
            </p>
          </div>
        ),
      },
    ],
  },
])

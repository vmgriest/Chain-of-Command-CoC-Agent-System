/**
 * Vite entry point.
 *
 * NOTE: StrictMode double-invokes effects in dev, which opens the WebSocket
 * twice in quick succession. useWebSocket cleans up properly on unmount (its
 * effect closes the socket with code 1000 and clears the reconnect timer), so
 * this is where a leak would show up first if that ever regresses.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

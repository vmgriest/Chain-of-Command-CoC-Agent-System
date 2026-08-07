/**
 * Vite entry point.
 */

// TODO(M1):
//   import React from 'react';
//   import ReactDOM from 'react-dom/client';
//   import App from './App';
//   import './index.css';
//
//   ReactDOM.createRoot(document.getElementById('root')!).render(
//     <React.StrictMode><App /></React.StrictMode>
//   );
//
// NOTE: StrictMode double-invokes effects in dev, which will open the WebSocket
//   twice. useWebSocket must clean up properly on unmount — if it does not, this
//   is where it shows up first, and it looks like a server bug.

export {};

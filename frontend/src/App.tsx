import React, { useEffect, useState } from 'react';

export default function App() {
  const [health, setHealth] = useState<string>('checking...');

  useEffect(() => {
    fetch('/health')
      .then((res) => res.json())
      .then((data) => setHealth(JSON.stringify(data)))
      .catch((err) => setHealth(`Error: ${err.message}`));
  }, []);

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>Enterprise Platform Dashboard</h1>
      <p>API Health: <code>{health}</code></p>
    </div>
  );
}

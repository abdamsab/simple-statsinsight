import React, { useState } from 'react';
import './App.css'; // Assuming Vite created this, or link to your CSS

function App() {
  const [backendMessage, setBackendMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchMessage = async () => {
    setLoading(true);
    setError(null); // Clear previous errors
    setBackendMessage(''); // Clear previous message

    try {
      // *** IMPORTANT: This URL MUST match the address and port where your FastAPI backend is running ***
      // If Uvicorn is running on 127.0.0.1:8000, this is correct.
      const response = await fetch('https://orange-meme-g4ggvw76xj6h9gjg-8000.app.github.dev/');

      if (!response.ok) {
        // If the server responds with an error status (like 404 or 500)
        // We'll try to get more detail if the server sent JSON back
        try {
            const errorData = await response.json();
            throw new Error(`HTTP error! Status: ${response.status}, Detail: ${errorData.detail || JSON.stringify(errorData)}`);
        } catch (jsonError) {
             // If response wasn't JSON, just throw a generic error
             throw new Error(`HTTP error! Status: ${response.status}, Status Text: ${response.statusText}`);
        }
      }

      const data = await response.json();
      setBackendMessage(data.message); // Get the 'message' field from the JSON
      console.log("Message from backend:", data.message);

    } catch (e) {
      console.error("Failed to fetch message from backend:", e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Frontend Calling Backend</h1>
        <button onClick={fetchMessage} disabled={loading}>
          {loading ? 'Fetching...' : 'Fetch Greeting from Backend'}
        </button>
        {error && <p style={{ color: 'red' }}>Error: {error}</p>}
        {backendMessage && (
          <div>
            <h2>Message Received:</h2>
            <p>{backendMessage}</p>
          </div>
        )}
         {!loading && !backendMessage && !error && (
             <p>Click the button above to fetch a message from the backend.</p>
        )}
      </header>
    </div>
  );
}

export default App;

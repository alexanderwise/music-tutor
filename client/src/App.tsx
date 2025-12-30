import { BrowserRouter, Routes, Route } from "react-router-dom";
import { SongBrowser } from "./components/SongBrowser";
import { PlayerPage } from "./components/PlayerPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SongBrowser />} />
        <Route path="/player" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

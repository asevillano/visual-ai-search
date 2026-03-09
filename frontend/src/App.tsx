import { useState } from "react";
import Header from "./components/Layout/Header";
import UploadTab from "./components/Upload/UploadTab";
import SearchTab from "./components/Search/SearchTab";
import GalleryTab from "./components/Gallery/GalleryTab";

export type TabId = "search" | "upload" | "gallery";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("search");

  return (
    <div className="min-h-screen bg-gray-50">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="py-8 px-4 sm:px-6 lg:px-8">
        {activeTab === "search" && <SearchTab />}
        {activeTab === "upload" && <UploadTab />}
        {activeTab === "gallery" && <GalleryTab />}
      </main>
    </div>
  );
}

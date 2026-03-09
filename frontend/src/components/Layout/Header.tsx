import { useTranslation } from "react-i18next";
import { Globe, ScanSearch } from "lucide-react";
import LanguageToggle from "../common/LanguageToggle";
import type { TabId } from "../../App";

interface HeaderProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

const TABS: { id: TabId; labelKey: string }[] = [
  { id: "search", labelKey: "app.search" },
  { id: "upload", labelKey: "app.upload" },
  { id: "gallery", labelKey: "app.gallery" },
];

export default function Header({ activeTab, onTabChange }: HeaderProps) {
  const { t } = useTranslation();

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo + Title */}
          <div className="flex items-center gap-2">
            <ScanSearch className="h-8 w-8 text-blue-600" />
            <h1 className="text-xl font-bold text-gray-900">{t("app.title")}</h1>
          </div>

          {/* Tabs */}
          <nav className="flex space-x-1 bg-gray-100 rounded-lg p-1">
            {TABS.map(({ id, labelKey }) => (
              <button
                key={id}
                onClick={() => onTabChange(id)}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  activeTab === id
                    ? "bg-white text-blue-600 shadow-sm"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                {t(labelKey)}
              </button>
            ))}
          </nav>

          {/* Language Toggle */}
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-gray-500" />
            <LanguageToggle />
          </div>
        </div>
      </div>
    </header>
  );
}

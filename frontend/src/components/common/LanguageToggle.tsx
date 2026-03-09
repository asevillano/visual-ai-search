import { useTranslation } from "react-i18next";

export default function LanguageToggle() {
  const { i18n } = useTranslation();

  const toggle = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem("lang", lang);
  };

  return (
    <div className="flex items-center gap-1 text-sm">
      <button
        onClick={() => toggle("en")}
        className={`px-2 py-1 rounded ${
          i18n.language === "en"
            ? "bg-blue-100 text-blue-700 font-semibold"
            : "text-gray-500 hover:text-gray-800"
        }`}
      >
        EN
      </button>
      <span className="text-gray-300">|</span>
      <button
        onClick={() => toggle("es")}
        className={`px-2 py-1 rounded ${
          i18n.language === "es"
            ? "bg-blue-100 text-blue-700 font-semibold"
            : "text-gray-500 hover:text-gray-800"
        }`}
      >
        ES
      </button>
    </div>
  );
}

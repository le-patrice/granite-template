import React from "react";

export const Footer: React.FC = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-border py-4 px-6">
      <div className="flex flex-col items-center justify-between gap-4 sm:flex-row text-xs text-muted-foreground">
        <p>Full Stack Enterprise Platform - {currentYear}</p>
        <div className="flex items-center gap-4">
          <span className="font-mono text-[11px]">Powered by Litestar + TimescaleDB</span>
        </div>
      </div>
    </footer>
  );
};

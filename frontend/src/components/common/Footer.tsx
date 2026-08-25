import React from "react";

export const Footer: React.FC = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-border py-4 px-6">
      <div className="flex flex-col items-center justify-between gap-4 sm:flex-row text-xs text-muted-foreground">
        <p>Full Stack Platform Template - {currentYear}</p>
        <div className="flex items-center gap-4">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="hover:text-foreground transition-colors"
          >
            API Docs
          </a>
          <span className="text-border">|</span>
          <span className="font-mono text-[11px]">Litestar + TimescaleDB</span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;

import { href } from "../router";
import { RETENTION_DAYS } from "../types";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="shell">
        <p>Human Cutout is a portfolio project. Your uploads are deleted after {RETENTION_DAYS} days.</p>
        <nav aria-label="Footer">
          <a href={href("privacy")}>Your privacy</a>
          <a href="https://github.com/ATHARVA-87/human-cutout-studio" target="_blank" rel="noreferrer">
            Source code
          </a>
        </nav>
      </div>
    </footer>
  );
}

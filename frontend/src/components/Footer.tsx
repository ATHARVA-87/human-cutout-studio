import { href } from "../router";
import { RETENTION_DAYS } from "../types";

export function Footer() {
  return (
    <footer className="site-footer">
      <span>Human Cutout · a portfolio project · uploads are deleted after {RETENTION_DAYS} days</span>
      <nav>
        <a href={href("privacy")}>Privacy Notice</a>
        <a href="https://github.com/ATHARVA-87/human-cutout-studio" target="_blank" rel="noreferrer">
          Source code
        </a>
      </nav>
    </footer>
  );
}

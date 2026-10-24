import { RETENTION_DAYS } from "../types";

const LAST_UPDATED = "24 October 2026";
const CONTACT_URL = "https://github.com/ATHARVA-87";

/** The public Privacy Notice (reachable without signing in at /#/privacy). */
export function PrivacyPage() {
  return (
    <article className="legal">
      <p className="eyebrow">Legal</p>
      <h1>Privacy Notice</h1>
      <p className="muted">Last updated: {LAST_UPDATED}</p>

      <p>
        Human Cutout is a free, non-commercial portfolio project that cuts people out of photos with a machine-learning model. This
        notice explains what personal data the service handles, why, for how long, and what choices you have. In short: we keep only what
        is needed to run the service, your photos are deleted automatically after {RETENTION_DAYS} days, and nothing is sold, shared for
        advertising, or used to train models.
      </p>

      <h2>1. Who is responsible</h2>
      <p>
        The service is run by its developer as a personal project (GitHub:{" "}
        <a href={CONTACT_URL} target="_blank" rel="noreferrer">
          ATHARVA-87
        </a>
        ). For any privacy question or request, contact the developer through that profile.
      </p>

      <h2>2. What we collect</h2>
      <ul>
        <li>
          <strong>Account data:</strong> your email address and your password. The password is never stored; only a salted, slow hash of
          it (PBKDF2-SHA256) is kept.
        </li>
        <li>
          <strong>Your content:</strong> photos you upload, the masks, cutouts and compositions generated from them, the original file name
          and image size.
        </li>
        <li>
          <strong>Usage records:</strong> your credit balance and credit history, rate-limit counters, and records of failed sign-in attempts
          (stored as a one-way hash of the email address, not the address itself).
        </li>
        <li>
          <strong>Technical data:</strong> a session cookie (see section 5). The application logs each API request with its method, path,
          status, duration and a random request ID; it does not log email addresses, passwords or photos. Our hosting provider may
          process IP addresses to deliver and protect the service.
        </li>
      </ul>
      <p>We do not collect payment details, location, contacts, or any data from other websites.</p>

      <h2>3. Why we use it</h2>
      <ul>
        <li>To provide the service you asked for: sign-in, processing your photos, showing your history, and counting credits.</li>
        <li>To keep the service secure and fair: preventing password guessing, abuse and overload (rate limits).</li>
      </ul>
      <p>
        We do <strong>not</strong> use your photos or results to train or improve the model, we do not sell or rent personal data, we do
        not show advertising, and we do not build profiles about you.
      </p>

      <h2>4. How long we keep it</h2>
      <table>
        <thead>
          <tr>
            <th>Data</th>
            <th>Kept for</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Uploaded photos, generated images and their history entries</td>
            <td>{RETENTION_DAYS} days, then deleted automatically (or earlier if you delete them)</td>
          </tr>
          <tr>
            <td>Failed sign-in records</td>
            <td>1 day</td>
          </tr>
          <tr>
            <td>Credit history</td>
            <td>30 days</td>
          </tr>
          <tr>
            <td>Login session</td>
            <td>Until you log out, sign in elsewhere, or 7 days pass</td>
          </tr>
          <tr>
            <td>Account (email, password hash, credit balance)</td>
            <td>Until you delete your account</td>
          </tr>
        </tbody>
      </table>
      <p>
        On the free hosting plan, generated images are stored on temporary server storage and may disappear earlier, for example when the
        server restarts. Download anything you want to keep.
      </p>

      <h2>5. Cookies and local storage</h2>
      <ul>
        <li>
          <strong>human_cutout_session</strong>: a strictly necessary cookie that keeps you signed in. It is HTTP-only (scripts cannot read
          it), sent only over HTTPS, and expires after 7 days.
        </li>
        <li>
          <strong>theme</strong> (browser local storage): remembers whether you chose the light or dark theme.
        </li>
      </ul>
      <p>
        There are no analytics, advertising or tracking cookies, and the site loads no third-party scripts or fonts. Because only strictly
        necessary storage is used, no cookie consent banner is needed.
      </p>

      <h2>6. Who processes the data</h2>
      <p>The service runs on two infrastructure providers that process data only on our behalf:</p>
      <ul>
        <li>
          <strong>Render</strong>: application hosting (runs the website and stores generated images temporarily).
        </li>
        <li>
          <strong>Neon</strong>: managed PostgreSQL database (stores accounts, credits and history entries).
        </li>
      </ul>
      <p>
        Both are configured to run in the Singapore region. The model file is downloaded from Hugging Face when the server is built; your
        data is never sent there. No other third parties receive your data.
      </p>

      <h2>7. How we protect it</h2>
      <p>
        HTTPS everywhere, hashed passwords and session tokens, HTTP-only session cookies, one active session per account, per-user access
        checks on every request, rate limits on jobs and sign-in attempts, and strict browser security headers. Generated images are served
        from long, random, unguessable links; anyone who has an exact link can open that image until it is deleted, so do not share links to
        images you want to keep private.
      </p>

      <h2>8. Your rights and choices</h2>
      <ul>
        <li>
          <strong>See your data:</strong> the History page shows everything stored from your uploads.
        </li>
        <li>
          <strong>Download it:</strong> every result has download buttons.
        </li>
        <li>
          <strong>Delete it:</strong> delete single items from History, or delete your whole account under History → Your data. Account
          deletion removes all of the data listed above immediately.
        </li>
        <li>
          <strong>Correct it:</strong> changing the email address is not supported; delete the account and create a new one.
        </li>
        <li>
          <strong>Complain:</strong> you can contact the developer, and you have the right to lodge a complaint with your local data
          protection authority.
        </li>
      </ul>

      <h2>9. Your responsibilities</h2>
      <p>
        Only upload photos you have the right to use. If a photo shows other people, make sure they agree. Do not upload sensitive images.
      </p>

      <h2>10. Children</h2>
      <p>The service is not intended for anyone under 16, and we do not knowingly collect their data.</p>

      <h2>11. Changes</h2>
      <p>If this notice changes, the new version is published on this page with a new "Last updated" date.</p>
    </article>
  );
}

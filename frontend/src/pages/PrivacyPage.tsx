import { RETENTION_DAYS } from "../types";

const LAST_UPDATED = "24 October 2026";
const CONTACT_URL = "https://github.com/ATHARVA-87";

/** The public privacy notice (reachable without signing in at /#/privacy), written from the reader's side. */
export function PrivacyPage() {
  return (
    <article className="legal">
      <h1 className="page-title">Your privacy</h1>
      <p className="soft">Last updated {LAST_UPDATED}</p>

      <p>
        This page explains what happens to your information when you use Human Cutout, a free portfolio project that cuts people out of
        photos. The short version: you share only an email address, a password and the photos you choose to upload. Your photos and results
        are deleted after {RETENTION_DAYS} days, they are never used to train the model, and nothing about you is sold or used for
        advertising.
      </p>

      <h2>1. Who you can contact</h2>
      <p>
        Human Cutout is run by one developer as a personal project. If you have a question or want something done with your data, contact
        them through their GitHub profile:{" "}
        <a href={CONTACT_URL} target="_blank" rel="noreferrer">
          ATHARVA-87
        </a>
        .
      </p>

      <h2>2. What you share, and what's kept</h2>
      <ul>
        <li>
          <strong>Your account:</strong> your email address and your password. Your password itself is never stored, only a salted, slow
          hash of it (PBKDF2-SHA256), so nobody can read it back.
        </li>
        <li>
          <strong>Your photos and results:</strong> the photos you upload, the masks, cutouts and combined photos made from them, where you
          placed the person in the editor, and each photo's file name and size.
        </li>
        <li>
          <strong>Your credits and activity:</strong> your credit balance and history, a counter that limits how many jobs you can start,
          and a record of failed sign-in attempts on your email address. That record stores a one-way hash of the address, not the address
          itself.
        </li>
        <li>
          <strong>Your browser session:</strong> a cookie that keeps you signed in (see section 5). Each request you make is logged with its
          type, address, result, duration and a random ID. Your email address, password and photos are never written to these logs. The
          hosting provider may see your IP address while delivering the site and protecting it from attacks.
        </li>
      </ul>
      <p>You are never asked for payment details, your location or your contacts, and nothing is read from other websites you visit.</p>

      <h2>3. How your information is used</h2>
      <ul>
        <li>To give you what you ask for: signing you in, processing your photos, showing your history and counting your credits.</li>
        <li>To keep your account and the service safe: blocking password guessing, abuse and overload.</li>
      </ul>
      <p>
        Your photos and results are <strong>never</strong> used to train or improve the model. Your information is not sold or rented, you
        won't see advertising, and no profile is built about you.
      </p>

      <h2>4. How long your data is kept</h2>
      <table>
        <thead>
          <tr>
            <th>Your data</th>
            <th>Kept for</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Your uploaded photos, results, editor positions and history</td>
            <td>{RETENTION_DAYS} days, then deleted automatically. You can delete them sooner yourself.</td>
          </tr>
          <tr>
            <td>Failed sign-in attempts on your email</td>
            <td>1 day</td>
          </tr>
          <tr>
            <td>Your credit history</td>
            <td>30 days</td>
          </tr>
          <tr>
            <td>Your sign-in session</td>
            <td>Until you log out, sign in on another device, or 7 days pass</td>
          </tr>
          <tr>
            <td>Your account (email, password hash, credit balance)</td>
            <td>Until you delete your account</td>
          </tr>
        </tbody>
      </table>
      <p>
        Because the site runs on a free hosting plan, your generated images sit on temporary server storage and can disappear sooner, for
        example when the server restarts. Download anything you want to keep.
      </p>

      <h2>5. Cookies and storage on your device</h2>
      <ul>
        <li>
          <strong>human_cutout_session:</strong> keeps you signed in. Scripts on the page can't read it, it's only sent over a secure (HTTPS)
          connection, and it expires after 7 days.
        </li>
        <li>
          <strong>theme</strong> (stored in your browser): remembers whether you picked the light or dark theme.
        </li>
      </ul>
      <p>
        Nothing else is stored on your device: no analytics, advertising or tracking cookies, and no scripts or fonts from other companies.
        Because only these strictly necessary items are used, you won't see a cookie banner.
      </p>

      <h2>6. Where your data is stored</h2>
      <p>Your data is handled by two infrastructure providers, only to run this service:</p>
      <ul>
        <li>
          <strong>Render</strong> runs the website and keeps your generated images for a short time.
        </li>
        <li>
          <strong>Neon</strong> hosts the database with your account, credits and history.
        </li>
      </ul>
      <p>
        Both run in Singapore. The model file is downloaded from Hugging Face when the site is built; your data is never sent there, and no
        one else receives it.
      </p>

      <h2>7. How your data is protected</h2>
      <p>
        Your connection is encrypted (HTTPS). Your password and session are stored only as hashes, your session cookie can't be read by
        scripts, and you can be signed in on only one device at a time. Every request checks that you can only see your own data, and limits
        stop people from guessing your password or flooding the service.
      </p>
      <p>
        Your images are served from long, random links that can't be guessed. Anyone who has the exact link to one of your images can open
        it until it's deleted, so don't share links to images you want to keep private.
      </p>

      <h2>8. Your choices and rights</h2>
      <ul>
        <li>
          <strong>See your data:</strong> the History page shows everything kept from your uploads.
        </li>
        <li>
          <strong>Take a copy:</strong> every result has download buttons.
        </li>
        <li>
          <strong>Delete it:</strong> delete single items from History, or delete your whole account at the bottom of the History page.
          Deleting your account removes everything listed above immediately.
        </li>
        <li>
          <strong>Change it:</strong> you can't change your email address yet; delete your account and create a new one instead.
        </li>
        <li>
          <strong>Complain:</strong> contact the developer, or the data protection authority where you live.
        </li>
      </ul>

      <h2>9. Photos of other people</h2>
      <p>
        Only upload photos you have the right to use. If a photo shows other people, make sure they're okay with it, and don't upload
        sensitive images.
      </p>

      <h2>10. Age</h2>
      <p>You need to be at least 16 to use Human Cutout.</p>

      <h2>11. When this page changes</h2>
      <p>If anything here changes, the new version appears on this page with a new "Last updated" date.</p>
    </article>
  );
}

# Security policy

## Supported versions

Only the latest release gets security fixes. Install it pinned to its tag, as the README shows, and upgrade when a new release says it fixes a security problem.

## Reporting a vulnerability

Please report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue, and do not include real mail in the report; a synthetic message that shows the problem is enough.

You can expect an answer within two weeks. This is a one-person project maintained in spare time, so a fix may take longer, but you will be told what is planned and credited in the changelog unless you prefer otherwise.

## What counts

Anything that breaks a promise in the README's security model, for example:

- mail excluded by the privacy filter reaching the assistant through any tool;
- a tool writing to the Thunderbird profile, or sending, moving or deleting mail;
- an email getting `compose` to attach a file from outside the allowed folders, or to add a recipient or field the assistant did not pass;
- the server running a program other than Thunderbird;
- mail text written to `audit.log`.

Out of scope: an assistant that follows instructions found in an email when your client lets it act without asking (see the README on tool permissions), and attacks that need someone who can already write to your profile or your user folders.

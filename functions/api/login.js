// Visit /api/login to sign in through Access; once through, it sends you back to the site.
export const onRequestGet = ({ request }) => Response.redirect(new URL('/', request.url).href, 302);

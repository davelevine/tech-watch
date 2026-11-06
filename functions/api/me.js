// Lets the page check whether reader mode is available (Access lets the request through).
export const onRequestGet = () => new Response('{"reader":true}', {
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

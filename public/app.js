const form = document.querySelector('#shorten-form');
const input = document.querySelector('#url');
const message = document.querySelector('#form-message');
const result = document.querySelector('#result');
const shortUrl = document.querySelector('#short-url');
const copyButton = document.querySelector('#copy-button');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = '';
  result.hidden = true;
  const button = form.querySelector('button');
  button.disabled = true;
  button.querySelector('span').textContent = 'Criando...';

  try {
    const response = await fetch('/api/links', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: input.value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Não foi possível encurtar este link.');
    shortUrl.href = data.shortUrl;
    shortUrl.textContent = data.shortUrl;
    result.hidden = false;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.querySelector('span').textContent = 'Encurtar link';
  }
});

copyButton.addEventListener('click', async () => {
  await navigator.clipboard.writeText(shortUrl.href);
  copyButton.firstChild.textContent = 'Copiado! ';
  setTimeout(() => { copyButton.firstChild.textContent = 'Copiar '; }, 1600);
});
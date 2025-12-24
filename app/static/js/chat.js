document.addEventListener('DOMContentLoaded', ()=>{
  const form = document.getElementById('chatForm')
  const msgInput = document.getElementById('msg')
  const box = document.getElementById('chatbox')
  form.addEventListener('submit', async (e)=>{
    e.preventDefault()
    const text = msgInput.value.trim()
    if(!text) return
    append('You', text)
    msgInput.value = ''
    try{
      const res = await fetch('/agent/chat', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message: text})
      })
      const j = await res.json()
      append('Agent', j.reply)
    }catch(err){
      append('Agent','Error: '+err.message)
    }
  })
  function append(who, text){
    const el = document.createElement('div')
    el.className='msg'
    el.innerHTML = `<span class="user">${who}:</span> ${escapeHtml(text)}`
    box.appendChild(el)
    box.scrollTop = box.scrollHeight
  }
  function escapeHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
})

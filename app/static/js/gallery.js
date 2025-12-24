document.addEventListener('DOMContentLoaded', ()=>{
  // helper to POST JSON and parse response
  async function jsonPost(url, body){
    const res = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    })
    try{ return await res.json() }catch(e){ return null }
  }

  // Create folder (AJAX)
  document.querySelectorAll('.ajax-create-folder').forEach(form=>{
    form.addEventListener('submit', async (e)=>{
      e.preventDefault()
      const name = form.querySelector('input[name="name"]').value.trim()
      if(!name) return alert('Enter a folder name')
      const j = await jsonPost('/api/create_folder', {name})
      if(j && j.ok) location.reload()
      else alert('Error creating folder')
    })
  })

  // Delete folder (AJAX)
  document.querySelectorAll('.ajax-delete-folder').forEach(form=>{
    form.addEventListener('submit', async (e)=>{
      e.preventDefault()
      if(!confirm('Delete folder and all images?')) return
      const qp = new URLSearchParams(window.location.search)
      const folder = qp.get('folder')
      const j = await jsonPost('/api/delete_folder', {folder})
      if(j && j.ok) location.href = '/gallery'
      else alert('Error deleting folder')
    })
  })

  // Delete image (AJAX)
  document.querySelectorAll('.ajax-delete-image').forEach(form=>{
    form.addEventListener('submit', async (e)=>{
      e.preventDefault()
      if(!confirm('Remove this image?')) return
      const fd = new FormData(form)
      const filename = fd.get('filename')
      const qp = new URLSearchParams(window.location.search)
      const folder = qp.get('folder')
      const j = await jsonPost('/api/delete_image', {folder, filename})
      if(j && j.ok){
        const fig = form.closest('figure')
        if(fig) fig.remove()
      }else alert('Error removing image')
    })
  })

  // EXIF view
  document.querySelectorAll('.btn-exif').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const folder = btn.dataset.folder || ''
      const filename = btn.dataset.filename
      const params = new URLSearchParams({folder, filename})
      const res = await fetch('/api/image_exif?'+params.toString())
      let j = null
      try{ j = await res.json() }catch(e){ j = null }
      showModal(j && j.exif ? JSON.stringify(j.exif, null, 2) : 'No EXIF')
    })
  })

  // Simple modal for EXIF
  function showModal(text){
    let modal = document.getElementById('exif-modal')
    if(!modal){
      modal = document.createElement('div')
      modal.id = 'exif-modal'
      modal.innerHTML = '<div class="modal-inner"><pre id="exif-pre"></pre><div style="text-align:right"><button id="exif-close">Close</button></div></div>'
      document.body.appendChild(modal)
      document.getElementById('exif-close').addEventListener('click', ()=> modal.remove())
    }
    const pre = document.getElementById('exif-pre')
    if(pre) pre.textContent = text
  }

})

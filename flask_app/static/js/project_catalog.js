/** Bounded project search for the retained server-rendered analysis page. */
window.ProjectCatalogSelect = class {
    constructor(select, initialValue = '') {
        this.select = select; this.value = initialValue || select.value; this.page = 1; this.search = ''; this.version = 0;
        this.pinned = this.value && select.value === this.value ? {id:this.value, name:select.selectedOptions[0]?.textContent || '当前项目'} : null;
        this.controls = document.createElement('div'); this.controls.className = 'd-grid gap-2 mb-2';
        this.input = document.createElement('input'); this.input.className = 'form-control'; this.input.type = 'search'; this.input.placeholder = '按项目名称或机构搜索'; this.input.setAttribute('aria-label','搜索分析项目');
        this.status = document.createElement('span'); this.status.className = 'small text-muted'; this.status.setAttribute('role','status');
        this.pages = document.createElement('div'); this.pages.className = 'd-flex gap-2 flex-wrap';
        this.previous = this.button('上一页',()=>this.load(this.page-1)); this.next = this.button('下一页',()=>this.load(this.page+1)); this.retry = this.button('重新读取项目',()=>this.load(this.page)); this.retry.hidden = true;
        this.pages.append(this.previous,this.next,this.retry); this.controls.append(this.input,this.status,this.pages); select.before(this.controls);
        this.input.addEventListener('input',()=>{clearTimeout(this.timer);this.timer=setTimeout(()=>{this.search=this.input.value.trim();this.load(1);},300);});
        select.addEventListener('change',()=>{this.value=select.value;this.pinned=this.value?{id:this.value,name:select.selectedOptions[0]?.textContent || '当前项目'}:null;this.load(this.page);});
    }
    button(text,action){const button=document.createElement('button');button.type='button';button.className='btn btn-sm btn-outline-primary';button.textContent=text;button.addEventListener('click',action);return button;}
    async load(page=1){
        const version=++this.version;this.page=Math.max(1,page);this.previous.disabled=true;this.next.disabled=true;this.retry.hidden=true;this.status.textContent='正在读取项目…';
        try{
            const params=new URLSearchParams({view:'selector',q:this.search,page:String(this.page),page_size:'20'});
            const response=await fetch('/api/projects?'+params);const data=await response.json();if(!response.ok)throw new Error(data.message || '项目读取失败');
            if(version!==this.version)return;
            const last=Math.max(1,data.pagination.total_pages);if(this.page>last)return this.load(last);
            if(this.value && !data.projects.some(project=>project.id===this.value) && (!this.pinned || this.pinned.name==='当前项目')){
                const current=await fetch('/api/projects/'+encodeURIComponent(this.value)+'?summary_only=true');
                if(!current.ok)throw new Error('当前项目名称读取失败');const project=await current.json();if(version!==this.version)return;this.pinned={id:project.id,name:project.name};
            }
            const current=data.projects.find(project=>project.id===this.value);if(current)this.pinned=current;
            this.select.replaceChildren(new Option('请选择项目（可选）',''));
            if(this.value && !current)this.select.add(new Option(this.pinned?.name || '当前项目',this.value));
            data.projects.forEach(project=>this.select.add(new Option(project.name,project.id)));this.select.value=this.value;
            this.previous.disabled=this.page<=1;this.next.disabled=this.page>=last;
            this.status.textContent=`共 ${data.pagination.total} 个匹配项目 · 第 ${this.page} / ${last} 页`;
        }catch(error){if(version!==this.version)return;this.status.textContent=error.message || '项目读取失败';this.retry.hidden=false;}
    }
};

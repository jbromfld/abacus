import {useEffect,useRef,useState} from 'react';
import {Upload,Trash2,LoaderCircle,Check,ArrowRight,Pause} from 'lucide-react';
import Modal from './Modal';
import {api,loadImport} from './api';
import {syncImportUpdate,importStage} from './batchStatus';
import type {Category,ImportJob,ImportUpdate} from './api';

type Item={id:string;file:File;account_id:string;period:string;status:'pending'|'uploading'|'uploaded'|'failed'|'exists';error:string;job?:ImportJob};
export default function BatchUploadDialog({accounts,month,initialAccount,latestReview,onClose,onPrepared,onReview}:{accounts:Category[];month:string;initialAccount:string;latestReview:ImportUpdate|null;onClose:()=>void;onPrepared:()=>void;onReview:(job:ImportJob,closeQueue?:boolean)=>void}){
 const [defaultAccount,setDefaultAccount]=useState(initialAccount||(accounts.length===1?accounts[0].id:''));
 const [defaultPeriod,setDefaultPeriod]=useState(month);
 const [items,setItems]=useState<Item[]>([]);const [busy,setBusy]=useState(false);const [stopping,setStopping]=useState(false);const [opening,setOpening]=useState(false);const [error,setError]=useState('');
 const stop=useRef(false);const mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;stop.current=true;};},[]);
 useEffect(()=>{setItems(items=>syncImportUpdate(items,latestReview));},[latestReview]);
 const update=(id:string,change:Partial<Item>)=>{if(mounted.current)setItems(rows=>rows.map(r=>r.id===id?{...r,...change}:r));};
 const pending=items.filter(i=>i.status==='pending'||i.status==='failed');
 const close=()=>{if(busy){stop.current=true;setStopping(true);}else onClose();};
 const upload=async()=>{
  const queue=pending;setBusy(true);setStopping(false);setError('');stop.current=false;let prepared=0;let single:ImportJob|undefined;
  try{
   for(const item of queue){
    if(stop.current||!mounted.current)break;
    update(item.id,{status:'uploading',error:''});
    try{
     if(item.file.size>15*1024*1024)throw new Error('Statements must be smaller than 15 MB.');
     if(!/\.(csv|pdf)$/i.test(item.file.name))throw new Error('Choose a CSV or PDF with selectable text.');
     const body=new FormData();body.set('account_id',item.account_id);body.set('period',item.period);body.set('file',item.file);
     const job=await api<ImportJob>('/imports','POST',body);prepared++;single=job;
     update(item.id,{status:'uploaded',job,error:''});
    }catch(e){const failure=e as Error&{status?:number};update(item.id,{status:failure.status===409?'exists':'failed',error:failure.message});}
   }
  }finally{
   if(mounted.current){setBusy(false);setStopping(false);onPrepared();if(prepared===1&&single&&items.length===1&&!stop.current)onReview(single,true);}
  }
 };
 const review=async(item:Item)=>{if(!item.job)return;setOpening(true);setError('');try{const job=await loadImport(item.job.id);update(item.id,{job});if(mounted.current)onReview(job);}catch(e){if(mounted.current)setError((e as Error).message);}finally{if(mounted.current)setOpening(false);}};
 const statuses={pending:'Ready to upload',uploading:'Uploading…',uploaded:'Prepared for review',failed:'Failed · retry available',exists:'Already uploaded'};
 return <Modal title="Upload statements" onClose={close}><p className="muted batch-intro">Choose one or more CSV/text-PDF files. Check the card and statement period for every file. Files are uploaded separately; transactions still require review and saving.</p><div className="form-grid"><label>Default card<select value={defaultAccount} disabled={busy} onChange={e=>setDefaultAccount(e.target.value)}><option value="">Choose account</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>Default statement period<input type="month" value={defaultPeriod} disabled={busy} onChange={e=>setDefaultPeriod(e.target.value)}/></label></div><div className="batch-add"><label className="file-field"><Upload size={24}/>Statement files<input type="file" accept=".csv,.pdf" multiple disabled={busy} onChange={e=>{const files=Array.from(e.target.files??[]);setItems(current=>[...current,...files.map(file=>({id:crypto.randomUUID(),file,account_id:defaultAccount,period:defaultPeriod,status:'pending' as const,error:''}))]);e.target.value='';}}/></label>{items.length>0&&<button className="text-button" disabled={busy||!defaultAccount||!defaultPeriod} onClick={()=>setItems(rows=>rows.map(r=>r.status==='uploaded'?r:{...r,account_id:defaultAccount,period:defaultPeriod,status:'pending',error:''}))}>Apply defaults to files awaiting upload</button>}</div>
 {!accounts.length&&<p className="notice">Add a card account in Settings first.</p>}{error&&<p className="notice danger" role="alert">{error}</p>}
 {items.length>0&&<><div className="batch-summary" role="status">{items.filter(i=>i.job?.status==='committed').length} saved · {items.filter(i=>i.status==='uploaded'&&!['committed','undone','deleted'].includes(i.job?.status??'')).length} awaiting review · {items.filter(i=>i.status==='exists').length} already uploaded · {items.filter(i=>i.status==='failed').length} failed · {items.filter(i=>i.status==='pending').length} pending</div><div className="table-scroll batch-table"><table><thead><tr><th>File</th><th>Card account</th><th>Statement period</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><strong>{item.file.name}</strong><small>{(item.file.size/1024).toFixed(1)} KB</small></td><td><select aria-label={`Card for ${item.file.name}`} value={item.account_id} disabled={busy||item.status==='uploaded'} onChange={e=>update(item.id,{account_id:e.target.value,status:'pending',error:''})}><option value="">Choose account</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></td><td><input aria-label={`Statement period for ${item.file.name}`} type="month" value={item.period} disabled={busy||item.status==='uploaded'} onChange={e=>update(item.id,{period:e.target.value,status:'pending',error:''})}/></td><td><span className="batch-status">{item.status==='uploading'?<LoaderCircle size={14} className="spin"/>:item.job&&importStage(item.job.status).saved?<Check size={14}/>:null}{item.job?importStage(item.job.status).label:statuses[item.status]}</span>{item.error&&<small className={item.status==='failed'?'red':''}>{item.error}</small>}</td><td>{item.job?.status==='deleted'?<button className="text-button" disabled={busy} onClick={()=>update(item.id,{job:undefined,status:'pending',error:''})}>Upload again</button>:item.job?<button className="text-button" disabled={busy||opening} onClick={()=>void review(item)}>{importStage(item.job.status).action} <ArrowRight size={14}/></button>:<button className="icon" disabled={busy} aria-label={`Remove ${item.file.name} from upload queue`} onClick={()=>setItems(rows=>rows.filter(r=>r.id!==item.id))}><Trash2 size={15}/></button>}</td></tr>)}</tbody></table></div></>}
 <p className="batch-help">One failed file won’t cancel the others. Retry uploads only retries pending/failed files. Already-uploaded files remain available in the main Statement imports list. For batches spanning multiple months, set each file’s statement period before uploading.</p><div className="modal-actions"><button className="secondary" onClick={close}>{busy?<><Pause size={14}/>{stopping?'Stopping after current file…':'Stop after current file'}</>: 'Done'}</button><button disabled={busy||!accounts.length||!pending.length||pending.some(i=>!i.account_id||!i.period)} onClick={()=>void upload()}><Upload size={15}/>{busy?'Uploading…':items.some(i=>i.status==='failed')?'Retry pending / failed uploads':`Upload ${pending.length||''} ${pending.length===1?'statement':'statements'}`}</button></div></Modal>;
}

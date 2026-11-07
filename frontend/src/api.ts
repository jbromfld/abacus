export type Category = {id:string;name:string};
export type Account = Category & {stale_alert_enabled:boolean;csv_mapping:Record<string,string|null>|null;last_information_date:string|null;days_since_update:number|null;stale:boolean};
export type PayeeRule = {id:string;payee:string;kind:string;category_id:string};
export type Settings = {currency:string;model:string;advisor_enabled:boolean};
export type Change = {id:string;month:string;amount:number;override:boolean};
export type Recurring = {id:string;name:string;kind:'payable'|'receivable';frequency:'monthly'|'annual';distribute_annual:boolean;category_id:string|null;start_month:string;end_month:string|null;ach_enabled:boolean;ach_day:number|null;ach_start_month:string|null;ach_account_id:string|null;changes:Change[]};
export type Purchase = {id:string;name:string;amount:number;month:string;category_id:string;notes:string;included:boolean};
export type Transaction = {id:string;date:string;description:string;amount:number;kind:string;category_id:string|null;account_id:string;import_id?:string;provenance?:{type?:string}};
export type Forecast = {month:string;income:number;expenses:number;remaining:number;deficit:boolean;actual_deficit:boolean;actual:{expenses:number;status:string;marked_complete:boolean;transaction_count:number};lines:{id:string;name:string;kind:string;amount:number;category_id:string|null}[]};
export type Trend = {month:string;forecast:number;income:number;actual:number|null;status:string;categories:Record<string,{actual:number|null;forecast:number}>};
export type ReviewRow = {date:string;description:string;amount:number;kind:string;category_id:string|null;selected:boolean;errors:string[];duplicate?:boolean;skip_duplicate?:boolean;source?:Record<string,unknown>;source_index?:number;classification?:string|null};
export type ImportSummary = {id:string;filename:string;period:string;status:string;account_id:string;error:string};
export type ImportJob = ImportSummary & {commit_summary?:{added:number;skipped:number}|null;rows:ReviewRow[];source:{type:string;headers:string[];preview:Record<string,string>[];mapping?:Record<string,string|null>;mapping_warning?:string|null}};
export async function api<T>(path:string, method='GET', body?:unknown,signal?:AbortSignal):Promise<T>{
 const response=await fetch('/api'+path,{method,signal,headers:body instanceof FormData?{}:body===undefined?{}:{'Content-Type':'application/json'},body:body instanceof FormData?body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const data=await response.json().catch(()=>({detail:'Unable to connect. Check that the Python server is running.'}));throw Object.assign(new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)),{status:response.status});}
 return response.json() as Promise<T>;
}
export function monthNow(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;}
export function shiftMonth(month:string,n:number){const [y,m]=month.split('-').map(Number);const d=new Date(y,m-1+n,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;}
export function actualMonthFor(budgetMonth:string,currentMonth=false){return currentMonth?budgetMonth:shiftMonth(budgetMonth,-1);}
export function monthLabel(month:string,short=false){return new Date(month+'-02T12:00:00').toLocaleDateString(undefined,{month:short?'short':'long',year:'numeric'});}
export function digits(currency:string){return currency==='JPY'?0:2;}
export function money(amount:number,currency:string){return new Intl.NumberFormat(undefined,{style:'currency',currency,maximumFractionDigits:digits(currency)}).format(amount/10**digits(currency));}
export function inputAmount(amount:number,currency:string){return (amount/10**digits(currency)).toFixed(digits(currency));}
export function minor(value:string,currency:string){if(!(digits(currency)===0 ? /^\d+$/.test(value) : /^\d+(?:\.\d{1,2})?$/.test(value)))throw new Error('Enter a positive amount with valid currency precision.');const n=Math.round(Number(value)*10**digits(currency));if(!Number.isSafeInteger(n)||n<=0)throw new Error('Enter a positive amount.');return n;}

export type ImportUpdate = {id:string;status:string};
export async function loadImport(id:string):Promise<ImportJob>{
 const job=await api<ImportJob>('/imports/'+id);
 if(job.source.type==='csv'&&!job.source.mapping&&['prepared','review','failed','interrupted'].includes(job.status))return api<ImportJob>(`/imports/${id}/mapping/default`,'POST');
 return job;
}

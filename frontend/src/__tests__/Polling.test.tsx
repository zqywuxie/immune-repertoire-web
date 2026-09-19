import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';
import { usePolling } from '../shared/hooks/usePolling';
afterEach(()=>{cleanup();vi.useRealTimers();});
it('does not restart polling when the inline fetch function changes on rerender',async()=>{
 vi.useFakeTimers();const request=vi.fn().mockResolvedValue('done');
 const hook=renderHook(()=>usePolling(()=>request(),3000));
 await act(async()=>{await Promise.resolve();});hook.rerender();
 expect(request).toHaveBeenCalledTimes(1);
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});expect(request).toHaveBeenCalledTimes(2);
});
it('discards old project responses and suspends subsequent polls when disabled',async()=>{
 vi.useFakeTimers();let old!: (value:string)=>void;
 const pending=new Promise<string>(resolve=>{old=resolve;});
 const request=vi.fn().mockReturnValueOnce(pending).mockResolvedValue('new');
 const hook=renderHook(({project})=>usePolling(()=>request(),null,[project]),{initialProps:{project:'old'}});
 hook.rerender({project:'new'});await act(async()=>{await Promise.resolve();});
 await act(async()=>{old('old');});expect(hook.result.current.data).toBe('new');
 await act(async()=>{await vi.advanceTimersByTimeAsync(9000);});expect(request).toHaveBeenCalledTimes(2);
});

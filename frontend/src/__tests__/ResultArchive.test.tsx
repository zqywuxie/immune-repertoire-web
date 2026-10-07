import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Stage5Results } from "../features/scripthub/stages/Stage5Results";
import * as jobs from "../shared/api/jobs";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it("只发起一次打包请求，失败保留选择并允许重试", async () => {
  const download = vi.spyOn(jobs, "downloadResultArchive").mockRejectedValueOnce(new Error("文件已移除")).mockResolvedValueOnce(undefined);
  const result = {success:true,job:{id:"one",module:"profile",status:"completed"},status:"completed",result:{},outputs:[{kind:"zip",url:"/one.zip",label:"结果包"}],assets:[]} as unknown as jobs.JobResultsResponse;
  render(<Stage5Results jobIds={["one"]} resultsByJobId={{one:result}} onReset={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", {name:"打包下载所选（1）"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("文件已移除");
  expect(download).toHaveBeenCalledWith([{job_id:"one",url:"/one.zip"}]);
  fireEvent.click(screen.getByRole("button", {name:"打包下载所选（1）"}));
  expect(download).toHaveBeenCalledTimes(2);
});

it("通过原生表单提交归档请求，避免将压缩包缓存在 Blob 中", async () => {
  const submittedForms: HTMLFormElement[] = [];
  vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function (this: HTMLFormElement) {
    submittedForms.push(this);
  });
  const createObjectURL = vi.spyOn(URL, "createObjectURL");
  const items = [{ job_id: "job-1", url: "/api/script-hub/results/report/result.csv" }];

  await jobs.downloadResultArchive(items);

  const submittedForm = submittedForms.at(-1);
  expect(submittedForm).toBeDefined();
  expect(submittedForm?.method).toBe("post");
  expect(submittedForm?.action).toContain("/api/jobs/results/archive");
  expect(new FormData(submittedForm!).get("items")).toBe(JSON.stringify(items));
  expect(submittedForm?.isConnected).toBe(false);
  expect(createObjectURL).not.toHaveBeenCalled();
});

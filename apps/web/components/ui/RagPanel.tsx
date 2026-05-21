import { Badge } from "./Badge";
import { Card } from "./Card";
import { ScoreCell } from "./ScoreCell";

export type RagCitation = {
  rank: number;
  title: string;
  score?: number;
  source?: string;
  chunk?: string;
};

export type RagClaim = {
  text: string;
  grounded: boolean;
  cite?: string;
};

type RagPanelProps = {
  retrievedDocs?: number;
  avgScore?: number;
  groundedClaims?: number;
  hallucinationRisk?: string;
  answerPreview?: string;
  citations?: RagCitation[];
  claims?: RagClaim[];
};

export function RagPanel({
  retrievedDocs = 0,
  avgScore,
  groundedClaims = 0,
  hallucinationRisk = "unknown",
  answerPreview,
  citations = [],
  claims = [],
}: RagPanelProps) {
  return (
    <div className="col">
      <div className="rag-header">
        <div className="rag-header__title">
          <Badge variant="rag">RAG</Badge>
          <strong>Grounding</strong>
        </div>
        <div><div className="rag-stat__label">Docs</div><div className="rag-stat__value">{retrievedDocs}</div></div>
        <div><div className="rag-stat__label">Score medio</div><div className="rag-stat__value">{avgScore === undefined ? "-" : <ScoreCell value={avgScore} />}</div></div>
        <div><div className="rag-stat__label">Claims</div><div className="rag-stat__value">{groundedClaims}</div></div>
        <div><div className="rag-stat__label">Risco</div><div className="rag-stat__value">{hallucinationRisk}</div></div>
      </div>

      {answerPreview ? <Card title="Resposta gerada"><p className="muted">{answerPreview}</p></Card> : null}

      <div className="grid-2-eq">
        <Card title="Retrieval">
          <div className="citation-list">
            {citations.map((citation) => (
              <div className="citation" key={`${citation.rank}-${citation.title}`}>
                <div className="citation__rank">{citation.rank}</div>
                <div className="citation__body">
                  <div className="citation__title">{citation.title}</div>
                  <div className="citation__meta">{citation.source ?? citation.chunk ?? "-"}</div>
                </div>
                <div className="citation__score">{citation.score === undefined ? "-" : citation.score.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Claims">
          <div>
            {claims.map((claim) => (
              <div className={`claim-row ${claim.grounded ? "claim-row--ok" : "claim-row--ng"}`} key={claim.text}>
                <Badge variant={claim.grounded ? "ok" : "warn"}>{claim.grounded ? "ok" : "review"}</Badge>
                <span className="muted">{claim.text}</span>
                <span className="faint mono">{claim.cite ?? "-"}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

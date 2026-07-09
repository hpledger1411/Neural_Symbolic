"""API routes for workflow management."""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID
from backend.database import get_db
from backend.api.schemas import WorkflowRuleRequest, WorkflowRuleResponse
from backend.models.workflow_rule import WorkflowRule
from backend.engine.rules_engine import RulesEngine
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/rules", response_model=List[WorkflowRuleResponse])
async def list_rules(
    rule_type: Optional[str] = None,
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """List all workflow rules."""
    try:
        stmt = select(WorkflowRule)
        
        if enabled_only:
            stmt = stmt.where(WorkflowRule.enabled == True)
        
        if rule_type:
            stmt = stmt.where(WorkflowRule.workflow_type == rule_type)
        
        stmt = stmt.order_by(WorkflowRule.priority.desc(), WorkflowRule.created_at.desc())
        result = await db.execute(stmt)
        rules = result.scalars().all()
        
        return [
            {
                "id": r.id,
                "name": r.name,
                "workflow_type": r.workflow_type,
                "rule_config": r.rule_config,
                "enabled": r.enabled,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rules
        ]
    except Exception as e:
        logger.error(f"Failed to list rules: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/rules", response_model=WorkflowRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: WorkflowRuleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new workflow rule."""
    try:
        if not request.rule_config.get("conditions") or not request.rule_config.get("actions"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rule config must have 'conditions' and 'actions'",
            )
        
        rule = WorkflowRule(
            name=request.name,
            workflow_type=request.workflow_type,
            rule_config=request.rule_config,
            priority=request.priority,
            enabled=request.enabled,
            version=1,
        )
        
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        
        logger.info(f"Workflow rule created: {rule.id} ({request.name})")
        
        return {
            "id": rule.id,
            "name": rule.name,
            "workflow_type": rule.workflow_type,
            "rule_config": rule.rule_config,
            "enabled": rule.enabled,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create rule: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/rules/{rule_id}", response_model=WorkflowRuleResponse)
async def get_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a specific workflow rule."""
    try:
        stmt = select(WorkflowRule).where(WorkflowRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalars().first()
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found",
            )
        
        return {
            "id": rule.id,
            "name": rule.name,
            "workflow_type": rule.workflow_type,
            "rule_config": rule.rule_config,
            "enabled": rule.enabled,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rule: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/rules/{rule_id}", response_model=WorkflowRuleResponse)
async def update_rule(
    rule_id: UUID,
    request: WorkflowRuleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a workflow rule."""
    try:
        stmt = select(WorkflowRule).where(WorkflowRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalars().first()
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found",
            )
        
        rule.name = request.name
        rule.workflow_type = request.workflow_type
        rule.rule_config = request.rule_config
        rule.priority = request.priority
        rule.enabled = request.enabled
        rule.version += 1
        rule.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(rule)
        
        logger.info(f"Workflow rule updated: {rule.id}")
        
        return {
            "id": rule.id,
            "name": rule.name,
            "workflow_type": rule.workflow_type,
            "rule_config": rule.rule_config,
            "enabled": rule.enabled,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update rule: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow rule (soft delete)."""
    try:
        stmt = select(WorkflowRule).where(WorkflowRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalars().first()
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found",
            )
        
        rule.enabled = False
        rule.updated_at = datetime.utcnow()
        
        await db.commit()
        
        logger.info(f"Workflow rule deleted: {rule_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete rule: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/execute")
async def execute_workflow(
    rule_id: UUID,
    context: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Execute a workflow rule against context."""
    try:
        stmt = select(WorkflowRule).where(WorkflowRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalars().first()
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found",
            )
        
        if not rule.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rule is disabled",
            )
        
        rules_engine = RulesEngine()
        exec_result = await rules_engine.apply_rules(
            rule_type=rule.workflow_type,
            context=context,
            rules=[rule.rule_config],
        )
        
        rule.execution_count += 1
        rule.last_execution = datetime.utcnow()
        
        if exec_result.get("actions_triggered"):
            successful = sum(1 for a in exec_result["actions_triggered"] if a.get("success", True))
            rule.success_rate = (rule.success_rate * (rule.execution_count - 1) + (successful / len(exec_result["actions_triggered"]) * 100)) / rule.execution_count
        
        await db.commit()
        
        logger.info(f"Workflow executed: {rule_id}, actions triggered: {len(exec_result.get('actions_triggered', []))}")
        
        return exec_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute workflow: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
